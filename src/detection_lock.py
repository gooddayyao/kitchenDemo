"""Lock identity/color at high confidence, then track the object so the outline follows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple
import time

import cv2
import numpy as np

from src import config
from src.recipe_manager import Detection

_TERM = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 12, 1)


def _clip_roi(frame: np.ndarray, det: Detection) -> Tuple[np.ndarray, int, int]:
    h, w = frame.shape[:2]
    x1 = max(0, int(det.x1))
    y1 = max(0, int(det.y1))
    x2 = min(w, int(det.x2))
    y2 = min(h, int(det.y2))
    if x2 <= x1 or y2 <= y1:
        return np.empty((0, 0, 3), dtype=np.uint8), 0, 0
    bw, bh = x2 - x1, y2 - y1
    ix1 = x1 + int(bw * 0.18)
    iy1 = y1 + int(bh * 0.18)
    ix2 = x2 - int(bw * 0.18)
    iy2 = y2 - int(bh * 0.18)
    if ix2 <= ix1 or iy2 <= iy1:
        return frame[y1:y2, x1:x2], x1, y1
    return frame[iy1:iy2, ix1:ix2], ix1, iy1


def dominant_bgr(frame: np.ndarray, det: Detection) -> Tuple[int, int, int]:
    """Main object color (BGR), ignoring near-black / near-white pixels."""
    roi, _x, _y = _clip_roi(frame, det)
    if roi.size == 0:
        return (0, 200, 80)
    small = roi
    if max(roi.shape[:2]) > 64:
        scale = 64.0 / max(roi.shape[:2])
        small = cv2.resize(
            roi,
            (max(1, int(roi.shape[1] * scale)), max(1, int(roi.shape[0] * scale))),
            interpolation=cv2.INTER_AREA,
        )
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    keep = (sat >= 40) & (val >= 40) & (val <= 230)
    pixels = small[keep]
    if len(pixels) < 8:
        pixels = small.reshape(-1, 3)
    median = np.median(pixels, axis=0)
    color = (int(median[0]), int(median[1]), int(median[2]))
    return _boost_glow_color(color)


def _boost_glow_color(bgr: Tuple[int, int, int]) -> Tuple[int, int, int]:
    arr = np.uint8([[bgr]])
    hsv = cv2.cvtColor(arr, cv2.COLOR_BGR2HSV)[0, 0]
    h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])
    s = min(255, int(s * 1.25) + 50)
    v = min(255, max(v, 150))
    boosted = cv2.cvtColor(np.uint8([[[h, s, v]]]), cv2.COLOR_HSV2BGR)[0, 0]
    return int(boosted[0]), int(boosted[1]), int(boosted[2])


def _iou(a: Detection, b: Detection) -> float:
    x1 = max(a.x1, b.x1)
    y1 = max(a.y1, b.y1)
    x2 = min(a.x2, b.x2)
    y2 = min(a.y2, b.y2)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    area_a = max(1.0, (a.x2 - a.x1) * (a.y2 - a.y1))
    area_b = max(1.0, (b.x2 - b.x1) * (b.y2 - b.y1))
    return inter / (area_a + area_b - inter)


def _same_instance(locked: Detection, cand: Detection) -> bool:
    if _iou(locked, cand) >= 0.12:
        return True
    dx = locked.cx - cand.cx
    dy = locked.cy - cand.cy
    span = max(
        40.0,
        0.55
        * max(
            locked.x2 - locked.x1,
            locked.y2 - locked.y1,
            cand.x2 - cand.x1,
            cand.y2 - cand.y1,
        ),
    )
    return (dx * dx + dy * dy) ** 0.5 <= span * 2.2


def _window_from_det(det: Detection, frame: np.ndarray) -> Tuple[int, int, int, int]:
    h, w = frame.shape[:2]
    x = max(0, int(det.x1))
    y = max(0, int(det.y1))
    bw = max(8, int(det.x2 - det.x1))
    bh = max(8, int(det.y2 - det.y1))
    if x + bw > w:
        bw = max(8, w - x)
    if y + bh > h:
        bh = max(8, h - y)
    return (x, y, bw, bh)


def _center_size(det: Detection) -> Tuple[float, float, float, float]:
    w = max(8.0, det.x2 - det.x1)
    h = max(8.0, det.y2 - det.y1)
    return det.cx, det.cy, w, h


def _set_center_size(det: Detection, cx: float, cy: float, bw: float, bh: float) -> None:
    bw = max(8.0, bw)
    bh = max(8.0, bh)
    det.x1 = cx - bw * 0.5
    det.y1 = cy - bh * 0.5
    det.x2 = cx + bw * 0.5
    det.y2 = cy + bh * 0.5
    det.contour = None


def _ema_center_size(
    det: Detection,
    cx: float,
    cy: float,
    bw: float,
    bh: float,
    *,
    pos_alpha: float,
    size_alpha: float,
) -> None:
    ocx, ocy, obw, obh = _center_size(det)
    _set_center_size(
        det,
        (1.0 - pos_alpha) * ocx + pos_alpha * cx,
        (1.0 - pos_alpha) * ocy + pos_alpha * cy,
        (1.0 - size_alpha) * obw + size_alpha * bw,
        (1.0 - size_alpha) * obh + size_alpha * bh,
    )


def _hsv_hist(frame: np.ndarray, det: Detection) -> Optional[np.ndarray]:
    roi, _x, _y = _clip_roi(frame, det)
    if roi.size == 0:
        return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 40, 40), (180, 255, 230))
    hist = cv2.calcHist([hsv], [0, 1], mask, [24, 28], [0, 180, 0, 256])
    if float(cv2.norm(hist, cv2.NORM_L1)) < 8:
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 28], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 255, cv2.NORM_MINMAX)
    return hist


def _snapshot(det: Detection, color: Tuple[int, int, int]) -> Detection:
    return Detection(
        name=det.name,
        conf=float(det.conf),
        x1=float(det.x1),
        y1=float(det.y1),
        x2=float(det.x2),
        y2=float(det.y2),
        contour=None,
        locked=True,
        glow_color=color,
    )


@dataclass
class _Track:
    det: Detection
    hist: Optional[np.ndarray] = None
    window: Tuple[int, int, int, int] = (0, 0, 8, 8)
    missing_since: Optional[float] = None
    quality_peak: float = 0.0
    lock_bw: float = 8.0
    lock_bh: float = 8.0


class DetectionLock:
    """Lock class + glow color at ≥ threshold; track the box; drop when the object is gone."""

    def __init__(
        self,
        min_conf: Optional[float] = None,
        lost_sec: Optional[float] = None,
    ) -> None:
        self.min_conf = float(min_conf if min_conf is not None else config.LOCK_CONF)
        self.lost_sec = float(lost_sec if lost_sec is not None else config.LOCK_LOST_SEC)
        self._tracks: Dict[str, _Track] = {}

    @property
    def locked_names(self) -> Set[str]:
        return set(self._tracks.keys())

    def clear(self) -> None:
        self._tracks.clear()

    def update(
        self,
        frame: np.ndarray,
        detections: Sequence[Detection],
        *,
        detections_fresh: bool = True,
        now: Optional[float] = None,
    ) -> List[Detection]:
        now = time.monotonic() if now is None else now
        skip = {config.CONFIRM_OBJECT_CLASS}
        by_name: Dict[str, List[Detection]] = {}
        for det in detections:
            by_name.setdefault(det.name, []).append(det)

        lost: List[str] = []
        for name, track in self._tracks.items():
            quality = self._advance_camshift(frame, track)
            if track.quality_peak <= 0 and quality > 0:
                track.quality_peak = quality

            yolo_hit = False
            if detections_fresh:
                match = self._best_match(track.det, by_name.get(track.det.name) or [])
                if match is not None:
                    yolo_hit = True
                    mcx, mcy, _mw, _mh = _center_size(match)
                    dist = ((mcx - track.det.cx) ** 2 + (mcy - track.det.cy) ** 2) ** 0.5
                    # YOLO boxes jitter every few frames; only re-anchor if tracker drifted.
                    span = max(track.lock_bw, track.lock_bh)
                    if dist > max(28.0, 0.4 * span):
                        _ema_center_size(
                            track.det,
                            mcx,
                            mcy,
                            track.lock_bw,
                            track.lock_bh,
                            pos_alpha=0.35,
                            size_alpha=0.0,
                        )
                        track.window = _window_from_det(track.det, frame)

            peak = max(track.quality_peak, 1e-4)
            track_ok = quality >= 0.16 or quality >= 0.32 * peak
            if yolo_hit:
                seen = True
            elif detections_fresh:
                seen = False
            else:
                seen = track.missing_since is None and track_ok
            if seen:
                track.missing_since = None
                if quality > track.quality_peak:
                    track.quality_peak = quality
            else:
                if track.missing_since is None:
                    track.missing_since = now
                elif now - track.missing_since >= self.lost_sec:
                    lost.append(name)

        for name in lost:
            del self._tracks[name]

        ranked = sorted(detections, key=lambda d: float(d.conf), reverse=True)
        for det in ranked:
            if det.name in skip or det.name in self._tracks:
                continue
            if float(det.conf) >= self.min_conf:
                locked = _snapshot(det, dominant_bgr(frame, det))
                _cx, _cy, bw, bh = _center_size(locked)
                self._tracks[det.name] = _Track(
                    det=locked,
                    hist=_hsv_hist(frame, det),
                    window=_window_from_det(det, frame),
                    lock_bw=bw,
                    lock_bh=bh,
                )

        live = [
            det
            for det in detections
            if det.name not in self._tracks or det.name in skip
        ]
        return live + [t.det for t in self._tracks.values()]

    def _best_match(self, locked: Detection, cands: Sequence[Detection]) -> Optional[Detection]:
        scored: List[Tuple[float, Detection]] = []
        for cand in cands:
            if not _same_instance(locked, cand):
                continue
            scored.append((_iou(locked, cand) * 2.0 + float(cand.conf), cand))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]

    def _advance_camshift(self, frame: np.ndarray, track: _Track) -> float:
        """MeanShift keeps window size; only the center follows (less halo jitter)."""
        if track.hist is None:
            return 0.0
        h, w = frame.shape[:2]
        x, y, bw, bh = track.window
        if bw < 8 or bh < 8 or x >= w or y >= h:
            return 0.0
        try:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            back = cv2.calcBackProject([hsv], [0, 1], track.hist, [0, 180, 0, 256], 1)
            back = cv2.GaussianBlur(back, (9, 9), 0)
            _iters, window = cv2.meanShift(back, (x, y, bw, bh), _TERM)
        except cv2.error:
            return 0.0
        nx, ny, nw, nh = [int(v) for v in window]
        if nw < 8 or nh < 8 or nx + nw <= 0 or ny + nh <= 0:
            return 0.0
        nx = max(0, min(nx, w - 8))
        ny = max(0, min(ny, h - 8))
        nw = max(8, min(nw, w - nx))
        nh = max(8, min(nh, h - ny))
        roi = back[ny : ny + nh, nx : nx + nw]
        quality = float(np.mean(roi)) / 255.0 if roi.size else 0.0
        if quality < 0.08:
            return quality
        track.window = (nx, ny, nw, nh)
        tcx, tcy = nx + nw * 0.5, ny + nh * 0.5
        ocx, ocy, _obw, _obh = _center_size(track.det)
        if ((tcx - ocx) ** 2 + (tcy - ocy) ** 2) ** 0.5 < 2.2:
            return quality
        _ema_center_size(
            track.det,
            tcx,
            tcy,
            track.lock_bw,
            track.lock_bh,
            pos_alpha=0.32,
            size_alpha=0.0,
        )
        return quality
