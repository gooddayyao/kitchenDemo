"""Plane scale from a user-marked reference (e.g. cutting board).

Flow:
  1. Click 4 corners of the board (TL → TR → BR → BL)
  2. Enter real width / height in cm via on-screen trackbars
  3. Persist mm/px so cut guides can use recipe cut_spacing_mm
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from src import config

Point = Tuple[float, float]
CORNER_LABELS = ("左上", "右上", "右下", "左下")


@dataclass
class PlaneScale:
    mm_per_px: float
    width_mm: float
    height_mm: float
    corners: List[Point]  # TL, TR, BR, BL in pixel coords
    frame_w: int
    frame_h: int
    label: str = "砧板"

    def to_dict(self) -> dict:
        return {
            "mm_per_px": self.mm_per_px,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "corners": [[float(x), float(y)] for x, y in self.corners],
            "frame_w": self.frame_w,
            "frame_h": self.frame_h,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlaneScale":
        corners = [(float(p[0]), float(p[1])) for p in data["corners"]]
        return cls(
            mm_per_px=float(data["mm_per_px"]),
            width_mm=float(data["width_mm"]),
            height_mm=float(data["height_mm"]),
            corners=corners,
            frame_w=int(data.get("frame_w", 0)),
            frame_h=int(data.get("frame_h", 0)),
            label=str(data.get("label") or "砧板"),
        )

    def save(self, path: Path | str | None = None) -> Path:
        out = Path(path) if path else config.SCALE_CALIBRATION_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return out

    @classmethod
    def load(cls, path: Path | str | None = None) -> Optional["PlaneScale"]:
        src = Path(path) if path else config.SCALE_CALIBRATION_PATH
        if not src.exists():
            return None
        try:
            return cls.from_dict(json.loads(src.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None


def _dist(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def compute_mm_per_px(
    corners: Sequence[Point],
    width_mm: float,
    height_mm: float,
) -> float:
    """Average horizontal/vertical scale from a rectangle's 4 corners."""
    if len(corners) != 4:
        raise ValueError("Need exactly 4 corners (TL, TR, BR, BL)")
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("width_mm and height_mm must be > 0")

    tl, tr, br, bl = corners
    avg_w_px = (_dist(tl, tr) + _dist(bl, br)) / 2.0
    avg_h_px = (_dist(tl, bl) + _dist(tr, br)) / 2.0
    if avg_w_px < 1.0 or avg_h_px < 1.0:
        raise ValueError("Reference region too small in pixels")

    sx = width_mm / avg_w_px
    sy = height_mm / avg_h_px
    return (sx + sy) / 2.0


def cut_line_positions(length_px: float, spacing_px: float) -> List[float]:
    """Offsets along an axis for dashed cut guides (excludes endpoints)."""
    if length_px <= 0 or spacing_px <= 0:
        return []
    positions: List[float] = []
    t = spacing_px
    while t < length_px - 0.5:
        positions.append(t)
        t += spacing_px
    return positions


class ScaleCalibrator:
    """Interactive OpenCV UI: mark board → set cm → save PlaneScale."""

    def __init__(self, window_name: str | None = None) -> None:
        self.window_name = window_name or config.WINDOW_NAME
        self.corners: List[Point] = []
        self._phase = "corners"  # corners | size | done
        self._width_cm = 40
        self._height_cm = 30
        self.result: Optional[PlaneScale] = None

    def _on_mouse(self, event: int, x: int, y: int, _flags: int, _param: object) -> None:
        import cv2

        if self._phase != "corners":
            return
        if event == cv2.EVENT_LBUTTONDOWN and len(self.corners) < 4:
            self.corners.append((float(x), float(y)))
            if len(self.corners) == 4:
                self._phase = "size"

    def _on_width(self, val: int) -> None:
        self._width_cm = max(1, val)

    def _on_height(self, val: int) -> None:
        self._height_cm = max(1, val)

    def _placeholder(self, message: str, w: int = 960, h: int = 540) -> np.ndarray:
        import cv2

        img = np.full((h, w, 3), 40, dtype=np.uint8)
        cv2.putText(img, message, (40, h // 2 - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 255), 2)
        cv2.putText(
            img,
            "Waiting for camera frame...  [Q/ESC] skip",
            (40, h // 2 + 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (200, 200, 200),
            1,
        )
        return img

    def _draw(self, frame: np.ndarray) -> np.ndarray:
        import cv2

        out = frame.copy()
        h, w = out.shape[:2]
        banner = out.copy()
        cv2.rectangle(banner, (0, 0), (w, 110), (0, 0, 0), -1)
        cv2.addWeighted(banner, 0.55, out, 0.45, 0, out)

        if self._phase == "corners":
            n = len(self.corners)
            nxt = CORNER_LABELS[n] if n < 4 else ""
            cv2.putText(
                out,
                f"CLICK cutting board 4 corners  ({n}/4)",
                (12, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (255, 209, 102),
                2,
            )
            cv2.putText(
                out,
                f"Order: TL -> TR -> BR -> BL   next={nxt or 'done'}",
                (12, 62),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (240, 240, 240),
                1,
            )
            cv2.putText(
                out,
                "[R] reset points   [Q/ESC] skip calibration",
                (12, 92),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (180, 180, 180),
                1,
            )
        else:
            cv2.putText(
                out,
                f"Set REAL board size: {self._width_cm} x {self._height_cm} cm",
                (12, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 209, 102),
                2,
            )
            cv2.putText(
                out,
                "Use TOP trackbars width_cm / height_cm, then press Enter",
                (12, 62),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (240, 240, 240),
                1,
            )
            cv2.putText(
                out,
                "[Enter] save   [R] re-click corners   [Q/ESC] cancel",
                (12, 92),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (180, 180, 180),
                1,
            )

        if len(self.corners) >= 1:
            pts = np.array(self.corners, dtype=np.int32)
            for i, (x, y) in enumerate(self.corners):
                cv2.circle(out, (int(x), int(y)), 7, (0, 220, 0), -1)
                cv2.putText(
                    out,
                    CORNER_LABELS[i],
                    (int(x) + 8, int(y) - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 220, 0),
                    1,
                )
            if len(self.corners) >= 2:
                cv2.polylines(
                    out,
                    [pts],
                    isClosed=len(self.corners) == 4,
                    color=(0, 220, 0),
                    thickness=2,
                )

        if self._phase == "size" and len(self.corners) == 4:
            try:
                mm_per_px = compute_mm_per_px(
                    self.corners, self._width_cm * 10.0, self._height_cm * 10.0
                )
                cv2.putText(
                    out,
                    f"~{mm_per_px:.3f} mm/px  (1cm ≈ {10.0 / mm_per_px:.1f} px)",
                    (12, h - 16),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (180, 255, 180),
                    1,
                )
            except ValueError:
                pass

        return out

    def _confirm(self, frame_w: int, frame_h: int) -> bool:
        try:
            mm_per_px = compute_mm_per_px(
                self.corners, self._width_cm * 10.0, self._height_cm * 10.0
            )
        except ValueError as exc:
            print(f"[scale] invalid size: {exc}")
            return False
        self.result = PlaneScale(
            mm_per_px=mm_per_px,
            width_mm=self._width_cm * 10.0,
            height_mm=self._height_cm * 10.0,
            corners=list(self.corners),
            frame_w=frame_w,
            frame_h=frame_h,
            label="砧板",
        )
        self._phase = "done"
        return True

    def run(self, get_frame: Callable[[], Optional[np.ndarray]]) -> Optional[PlaneScale]:
        """Block until confirmed or cancelled. get_frame() returns BGR frame or None."""
        import cv2

        # Reuse existing main window when present; create otherwise.
        try:
            cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE)
        except cv2.error:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)

        cv2.setMouseCallback(self.window_name, self._on_mouse)

        print("[scale] === Cutting board scale calibration ===")
        print("[scale] Camera should already be visible in this window.")
        print("[scale] 1) Click 4 corners: 左上→右上→右下→左下")
        print("[scale] 2) Drag trackbars width_cm / height_cm to real size")
        print("[scale] 3) Press Enter to save   |  Q/ESC skip")

        last_frame: Optional[np.ndarray] = None
        trackbars_ready = False

        try:
            while True:
                frame = get_frame()
                if frame is not None:
                    last_frame = frame
                if last_frame is None:
                    cv2.imshow(
                        self.window_name,
                        self._placeholder("Waiting for camera frame…"),
                    )
                    key = cv2.waitKey(30) & 0xFF
                    if key in (27, ord("q")):
                        return None
                    continue

                if not trackbars_ready:
                    cv2.createTrackbar(
                        "width_cm", self.window_name, self._width_cm, 100, self._on_width
                    )
                    cv2.createTrackbar(
                        "height_cm", self.window_name, self._height_cm, 100, self._on_height
                    )
                    try:
                        cv2.setTrackbarMin("width_cm", self.window_name, 1)
                        cv2.setTrackbarMin("height_cm", self.window_name, 1)
                    except cv2.error:
                        pass
                    trackbars_ready = True

                fh, fw = last_frame.shape[:2]
                view = self._draw(last_frame)
                cv2.imshow(self.window_name, view)

                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    return None
                if key in (ord("r"), ord("R")):
                    self.corners.clear()
                    self._phase = "corners"
                    self.result = None
                if key in (13, 10) and self._phase == "size":  # Enter
                    if self._confirm(fw, fh):
                        assert self.result is not None
                        path = self.result.save()
                        print(
                            f"[scale] saved {path}  "
                            f"{self._width_cm}x{self._height_cm} cm → "
                            f"{self.result.mm_per_px:.4f} mm/px"
                        )
                        return self.result
        finally:
            # Leave window teardown to caller (main loop recreates without trackbars).
            try:
                cv2.setMouseCallback(self.window_name, lambda *args: None)
            except cv2.error:
                pass

        return None
