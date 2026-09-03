"""Multi-object local trackers seeded from Gemini (or any) bboxes.

Prefers OpenCV CSRT/KCF when available (opencv-contrib); otherwise uses a
template-matching tracker that works with stock opencv-python.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from src.recipe_manager import Detection


class TemplateTracker:
    """Lightweight fallback tracker (no opencv-contrib required)."""

    def __init__(self) -> None:
        self.template: Optional[np.ndarray] = None
        self.bbox = (0, 0, 1, 1)
        self.search_margin = 1.8  # search window vs template size

    def init(self, frame: np.ndarray, roi: Tuple[int, int, int, int]) -> bool:
        x, y, w, h = [int(v) for v in roi]
        fh, fw = frame.shape[:2]
        x = int(np.clip(x, 0, fw - 2))
        y = int(np.clip(y, 0, fh - 2))
        w = int(np.clip(w, 2, fw - x))
        h = int(np.clip(h, 2, fh - y))
        patch = frame[y : y + h, x : x + w]
        if patch.size == 0:
            return False
        self.template = patch.copy()
        self.bbox = (x, y, w, h)
        return True

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[float, float, float, float]]:
        if self.template is None or self.template.size == 0:
            return False, (0.0, 0.0, 1.0, 1.0)
        fh, fw = frame.shape[:2]
        x, y, w, h = self.bbox
        th, tw = self.template.shape[:2]
        cx = x + w / 2.0
        cy = y + h / 2.0
        sw = int(max(tw * self.search_margin, tw + 20))
        sh = int(max(th * self.search_margin, th + 20))
        x0 = int(np.clip(cx - sw / 2, 0, fw - 1))
        y0 = int(np.clip(cy - sh / 2, 0, fh - 1))
        x1 = int(np.clip(x0 + sw, 0, fw))
        y1 = int(np.clip(y0 + sh, 0, fh))
        roi = frame[y0:y1, x0:x1]
        if roi.shape[0] < th or roi.shape[1] < tw:
            return False, tuple(float(v) for v in self.bbox)

        res = cv2.matchTemplate(roi, self.template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val < 0.35:
            return False, tuple(float(v) for v in self.bbox)
        nx = x0 + max_loc[0]
        ny = y0 + max_loc[1]
        self.bbox = (nx, ny, tw, th)
        # Mildly refresh template to follow appearance change
        if max_val > 0.55:
            patch = frame[ny : ny + th, nx : nx + tw]
            if patch.shape[:2] == (th, tw):
                self.template = cv2.addWeighted(self.template, 0.85, patch, 0.15, 0)
        return True, (float(nx), float(ny), float(tw), float(th))


def _create_opencv_tracker():
    creators = []
    if hasattr(cv2, "TrackerCSRT_create"):
        creators.append(cv2.TrackerCSRT_create)
    if hasattr(cv2, "TrackerKCF_create"):
        creators.append(cv2.TrackerKCF_create)
    if hasattr(cv2, "TrackerMOSSE_create"):
        creators.append(cv2.TrackerMOSSE_create)
    legacy = getattr(cv2, "legacy", None)
    if legacy is not None:
        for name in ("TrackerCSRT_create", "TrackerKCF_create", "TrackerMOSSE_create"):
            if hasattr(legacy, name):
                creators.append(getattr(legacy, name))
    for fn in creators:
        try:
            return fn()
        except Exception:
            continue
    return None


def _create_tracker():
    native = _create_opencv_tracker()
    if native is not None:
        return native
    return TemplateTracker()


@dataclass
class TrackedTarget:
    track_id: int
    name: str
    label: str
    conf: float
    tracker: Any = field(repr=False)
    bbox_xywh: Tuple[float, float, float, float]  # pixels
    lost: bool = False
    lose_count: int = 0
    last_ok_at: float = field(default_factory=time.monotonic)

    def to_detection(self) -> Detection:
        x, y, w, h = self.bbox_xywh
        return Detection(
            name=self.name,
            conf=float(self.conf),
            x1=float(x),
            y1=float(y),
            x2=float(x + w),
            y2=float(y + h),
        )


class MultiObjectTracker:
    """Maintain trackers for Gemini-seeded targets."""

    def __init__(self, max_lose_frames: int = 20) -> None:
        self.max_lose_frames = max_lose_frames
        self._next_id = 1
        self.targets: List[TrackedTarget] = []
        self.last_seed_at: float = 0.0
        self.last_seed_error: str = ""
        self.status: str = "idle"  # idle | seeding | tracking | lost
        self.backend = "opencv" if _create_opencv_tracker() is not None else "template"

    def clear(self) -> None:
        self.targets.clear()
        self.status = "idle"

    @property
    def alive_count(self) -> int:
        return sum(1 for t in self.targets if not t.lost)

    def has_name(self, name: str) -> bool:
        return any(not t.lost and t.name == name for t in self.targets)

    def seed_from_detections(self, frame: np.ndarray, detections: Sequence[Detection]) -> int:
        self.targets.clear()
        h, w = frame.shape[:2]
        added = 0
        for det in detections:
            x1 = int(np.clip(det.x1, 0, w - 1))
            y1 = int(np.clip(det.y1, 0, h - 1))
            x2 = int(np.clip(det.x2, x1 + 2, w))
            y2 = int(np.clip(det.y2, y1 + 2, h))
            bw = x2 - x1
            bh = y2 - y1
            if bw < 8 or bh < 8:
                continue
            tracker = _create_tracker()
            ok = tracker.init(frame, (x1, y1, bw, bh))
            if ok is False:
                continue
            self.targets.append(
                TrackedTarget(
                    track_id=self._next_id,
                    name=det.name,
                    label=det.name,
                    conf=det.conf,
                    tracker=tracker,
                    bbox_xywh=(float(x1), float(y1), float(bw), float(bh)),
                    lost=False,
                    lose_count=0,
                )
            )
            self._next_id += 1
            added += 1
        self.last_seed_at = time.monotonic()
        self.status = "tracking" if added else "lost"
        return added

    def update(self, frame: np.ndarray) -> List[Detection]:
        if not self.targets:
            self.status = "lost"
            return []
        h, w = frame.shape[:2]
        out: List[Detection] = []
        for t in self.targets:
            ok, box = t.tracker.update(frame)
            if ok and box is not None:
                x, y, bw, bh = [float(v) for v in box]
                x = float(np.clip(x, 0, w - 1))
                y = float(np.clip(y, 0, h - 1))
                bw = float(np.clip(bw, 1, w - x))
                bh = float(np.clip(bh, 1, h - y))
                t.bbox_xywh = (x, y, bw, bh)
                t.lost = False
                t.lose_count = 0
                t.last_ok_at = time.monotonic()
                out.append(t.to_detection())
            else:
                t.lose_count += 1
                if t.lose_count >= self.max_lose_frames:
                    t.lost = True
                else:
                    out.append(t.to_detection())
        self.status = "tracking" if out else "lost"
        return out

    def target_lost(self, name: Optional[str] = None) -> bool:
        if not self.targets:
            return True
        if name:
            matched = [t for t in self.targets if t.name == name]
            if not matched:
                return True
            return all(t.lost for t in matched)
        return all(t.lost for t in self.targets)
