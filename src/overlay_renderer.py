"""OpenCV overlay: bbox, cut-lines, dropzone, occlusion buffer."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from src import config
from src.recipe_manager import Detection


class OcclusionBuffer:
    """Keep last detections for N frames when the target briefly disappears."""

    def __init__(self, max_frames: int = config.OCCLUSION_BUFFER_FRAMES) -> None:
        self.max_frames = max_frames
        self._store: Dict[str, Tuple[Detection, int]] = {}

    def update(self, detections: Sequence[Detection]) -> List[Detection]:
        seen = set()
        for det in detections:
            self._store[det.name] = (det, 0)
            seen.add(det.name)

        stale: List[str] = []
        for name, (det, age) in self._store.items():
            if name in seen:
                continue
            age += 1
            if age > self.max_frames:
                stale.append(name)
            else:
                self._store[name] = (det, age)

        for name in stale:
            del self._store[name]

        # Prefer live detections; fill gaps from buffer
        live_names = {d.name for d in detections}
        buffered = [det for name, (det, _) in self._store.items() if name not in live_names]
        return list(detections) + buffered

    def clear(self) -> None:
        self._store.clear()


class OverlayRenderer:
    def __init__(self) -> None:
        self.buffer = OcclusionBuffer()

    def render(
        self,
        frame: np.ndarray,
        detections: Sequence[Detection],
        *,
        highlight_class: Optional[str] = None,
        draw_cut_lines: bool = False,
        dropzone: Optional[dict] = None,
        instruction: str = "",
        step_label: str = "",
        timer_remaining: float = 0.0,
        hold_progress: Optional[float] = None,
    ) -> np.ndarray:
        out = frame.copy()
        h, w = out.shape[:2]
        stable = self.buffer.update(detections)

        if dropzone:
            self._draw_dropzone(out, dropzone, w, h)

        for det in stable:
            if det.name == config.CONFIRM_OBJECT_CLASS:
                color = (255, 180, 0)  # cyan-ish BGR for confirm mouse
                label = f"mouse CONFIRM {det.conf:.2f}"
                self._draw_bbox(out, det, color, label=label)
                continue
            is_target = highlight_class is None or det.name == highlight_class
            color = (0, 200, 0) if is_target else (0, 140, 255)  # green / orange (BGR)
            self._draw_bbox(out, det, color, label=f"{det.name} {det.conf:.2f}")
            if draw_cut_lines and is_target:
                self._draw_cut_lines(out, det)

        self._draw_hud(out, instruction, step_label, timer_remaining, hold_progress)
        return out

    def _draw_bbox(self, img: np.ndarray, det: Detection, color: Tuple[int, int, int], label: str) -> None:
        p1 = (int(det.x1), int(det.y1))
        p2 = (int(det.x2), int(det.y2))
        cv2.rectangle(img, p1, p2, color, 2)
        cv2.putText(img, label, (p1[0], max(20, p1[1] - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    def _draw_cut_lines(self, img: np.ndarray, det: Detection) -> None:
        """Three vertical dashed guide lines centered on the ingredient bbox."""
        x1, y1, x2, y2 = det.x1, det.y1, det.x2, det.y2
        n = config.CUT_LINE_COUNT
        color = (0, 255, 0)
        for i in range(1, n + 1):
            t = i / (n + 1)
            x = int(x1 + (x2 - x1) * t)
            self._dashed_line(img, (x, int(y1)), (x, int(y2)), color)

    def _dashed_line(
        self,
        img: np.ndarray,
        p1: Tuple[int, int],
        p2: Tuple[int, int],
        color: Tuple[int, int, int],
        dash: int = 10,
        gap: int = 8,
    ) -> None:
        x1, y1 = p1
        x2, y2 = p2
        length = max(1, int(np.hypot(x2 - x1, y2 - y1)))
        for i in range(0, length, dash + gap):
            a = i / length
            b = min(1.0, (i + dash) / length)
            qa = (int(x1 + (x2 - x1) * a), int(y1 + (y2 - y1) * a))
            qb = (int(x1 + (x2 - x1) * b), int(y1 + (y2 - y1) * b))
            cv2.line(img, qa, qb, color, 2)

    def _draw_dropzone(self, img: np.ndarray, dz: dict, w: int, h: int) -> None:
        x = int(dz["x"] * w)
        y = int(dz["y"] * h)
        rw = int(dz["w"] * w)
        rh = int(dz["h"] * h)
        color = (0, 220, 0)
        cv2.rectangle(img, (x, y), (x + rw, y + rh), color, 2)
        label = str(dz.get("label") or "dropzone")
        cv2.putText(img, label, (x + 6, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    def _draw_hud(
        self,
        img: np.ndarray,
        instruction: str,
        step_label: str,
        timer_remaining: float,
        hold_progress: Optional[float],
    ) -> None:
        h, w = img.shape[:2]
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (w, 78), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)

        title = step_label or "KITCHEN"
        cv2.putText(img, title, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 209, 102), 2)
        if instruction:
            text = instruction if len(instruction) < 90 else instruction[:87] + "..."
            cv2.putText(img, text, (12, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1)

        help_y = h - 16
        cv2.putText(
            img,
            "[Mouse→綠區2s] confirm  [N/Space] next  [Q/ESC] quit",
            (12, help_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (180, 180, 180),
            1,
        )

        if timer_remaining > 0:
            mm = int(timer_remaining) // 60
            ss = int(timer_remaining) % 60
            cv2.putText(
                img,
                f"TIMER {mm:02d}:{ss:02d}",
                (w - 160, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 200, 255),
                2,
            )

        if hold_progress is not None and hold_progress > 0:
            bar_w = int((w - 24) * min(1.0, hold_progress))
            cv2.rectangle(img, (12, h - 40), (12 + bar_w, h - 28), (0, 200, 255), -1)
