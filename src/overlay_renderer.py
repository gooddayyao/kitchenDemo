"""OpenCV overlay: bbox, cut-lines, ingredient checklist, occlusion buffer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from src import config
from src.ingredient_catalog import label_for
from src.recipe_manager import Detection
from src.scale_calibrator import cut_line_positions

try:
    from PIL import Image, ImageDraw, ImageFont

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

# Pending = bright cyan (conspicuous on kitchen bg); confirmed = green
_COLOR_PENDING = (0, 255, 255)  # BGR cyan
_COLOR_CONFIRMED = (60, 220, 90)  # BGR green
_COLOR_PANEL = (20, 20, 20)

_FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msjh.ttc"),
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\mingliu.ttc"),
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
]

_cached_font: Dict[int, Any] = {}


def _resolve_font(size: int):
    if not _HAS_PIL:
        return None
    if size in _cached_font:
        return _cached_font[size]
    for path in _FONT_CANDIDATES:
        if not path.exists():
            continue
        try:
            font = ImageFont.truetype(str(path), size=size, index=0)
            _cached_font[size] = font
            return font
        except OSError:
            continue
    try:
        font = ImageFont.load_default()
        _cached_font[size] = font
        return font
    except Exception:
        return None


def draw_text_bgr(
    img: np.ndarray,
    text: str,
    org: Tuple[int, int],
    color: Tuple[int, int, int],
    *,
    font_size: int = 22,
    thickness: int = 2,
) -> None:
    """Draw text (CJK-capable via Pillow when available). org = baseline-left."""
    draw_texts_bgr(img, [(text, org, color, font_size)], thickness=thickness)


def draw_texts_bgr(
    img: np.ndarray,
    items: Sequence[Tuple[str, Tuple[int, int], Tuple[int, int, int], int]],
    *,
    thickness: int = 2,
) -> None:
    """Batch-draw texts in one Pillow pass. Each item: (text, org, bgr, font_size)."""
    if not items:
        return

    if _HAS_PIL:
        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil)
        used_pil = False
        for text, org, color, font_size in items:
            font = _resolve_font(font_size)
            if font is None:
                continue
            used_pil = True
            x, y = org
            try:
                ascent, _ = font.getmetrics()
            except Exception:
                ascent = font_size
            top_left = (x, max(0, y - ascent))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
                draw.text((top_left[0] + dx, top_left[1] + dy), text, font=font, fill=(0, 0, 0))
            b, g, r = color
            draw.text(top_left, text, font=font, fill=(r, g, b))
        if used_pil:
            img[:, :, :] = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
            return

    for text, org, color, font_size in items:
        cv2.putText(
            img,
            text,
            org,
            cv2.FONT_HERSHEY_SIMPLEX,
            font_size / 32.0,
            color,
            thickness,
        )


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
        cut_spacing_mm: Optional[float] = None,
        mm_per_px: Optional[float] = None,
        dropzone: Optional[dict] = None,
        instruction: str = "",
        step_label: str = "",
        timer_remaining: float = 0.0,
        hold_progress: Optional[float] = None,
        scale_hint: str = "",
        ingredients: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> np.ndarray:
        out = frame.copy()
        h, w = out.shape[:2]
        stable = self.buffer.update(detections)

        # Dropzone confirm region is intentionally not drawn (was upper-right green box).
        _ = dropzone  # kept for API compatibility / future use

        for det in stable:
            if det.name == config.CONFIRM_OBJECT_CLASS:
                color = (255, 180, 0)  # cyan-ish BGR for confirm mouse
                label = f"{label_for(det.name)} CONFIRM {det.conf:.2f}"
                self._draw_detection(out, det, color, label=label)
                continue
            is_target = False
            if highlight_class is None:
                is_target = True
            else:
                is_target = det.name == highlight_class
                if not is_target:
                    # catalog id vs YOLO class (e.g. hot_dog vs "hot dog")
                    is_target = label_for(det.name) == label_for(highlight_class)
            color = (0, 200, 0) if is_target else (0, 140, 255)  # green / orange (BGR)
            nice = label_for(det.name)
            self._draw_detection(out, det, color, label=f"{nice} {det.conf:.2f}")
            if draw_cut_lines and is_target:
                self._draw_cut_lines(
                    out,
                    det,
                    cut_spacing_mm=cut_spacing_mm,
                    mm_per_px=mm_per_px,
                )

        self._draw_hud(
            out,
            instruction,
            step_label,
            timer_remaining,
            hold_progress,
            scale_hint=scale_hint,
        )
        if ingredients:
            self._draw_ingredient_checklist(out, list(ingredients))
        return out

    def _draw_detection(
        self,
        img: np.ndarray,
        det: Detection,
        color: Tuple[int, int, int],
        label: str,
    ) -> None:
        """Draw soft thick contour when available; otherwise axis-aligned bbox."""
        drawn_contour = False
        if det.contour is not None:
            try:
                cnt = np.asarray(det.contour)
                if cnt.size >= 6:
                    self._draw_soft_contour(img, cnt.astype(np.int32), color)
                    drawn_contour = True
            except Exception:
                drawn_contour = False

        if not drawn_contour:
            p1 = (int(det.x1), int(det.y1))
            p2 = (int(det.x2), int(det.y2))
            cv2.rectangle(img, p1, p2, color, 2)

        lx = int(det.x1)
        ly = max(20, int(det.y1) - 8)
        cv2.putText(img, label, (lx, ly), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    def _draw_soft_contour(
        self,
        img: np.ndarray,
        contour: np.ndarray,
        color: Tuple[int, int, int],
    ) -> None:
        """Thick anti-aliased stroke with a soft outer glow (less polygonal look)."""
        # Soften neon greens toward a gentler mint
        soft = (
            int(color[0] * 0.75 + 40),
            int(color[1] * 0.85 + 30),
            int(color[2] * 0.75 + 20),
        )
        soft = tuple(max(0, min(255, c)) for c in soft)

        glow = img.copy()
        cv2.drawContours(glow, [contour], -1, soft, thickness=14, lineType=cv2.LINE_AA)
        cv2.addWeighted(glow, 0.28, img, 0.72, 0, img)
        cv2.drawContours(img, [contour], -1, soft, thickness=6, lineType=cv2.LINE_AA)
        # Slightly brighter core for readability
        core = (
            min(255, soft[0] + 30),
            min(255, soft[1] + 20),
            min(255, soft[2] + 30),
        )
        cv2.drawContours(img, [contour], -1, core, thickness=2, lineType=cv2.LINE_AA)

    def _draw_cut_lines(
        self,
        img: np.ndarray,
        det: Detection,
        *,
        cut_spacing_mm: Optional[float] = None,
        mm_per_px: Optional[float] = None,
    ) -> None:
        """Cut guides: prefer real mm spacing; else equal split fallback."""
        x1, y1, x2, y2 = det.x1, det.y1, det.x2, det.y2
        bw = max(1.0, x2 - x1)
        bh = max(1.0, y2 - y1)
        color = (0, 255, 0)

        use_mm = (
            cut_spacing_mm is not None
            and cut_spacing_mm > 0
            and mm_per_px is not None
            and mm_per_px > 0
        )

        if use_mm:
            spacing_px = float(cut_spacing_mm) / float(mm_per_px)
            # Slice across the long axis (cucumber length).
            if bw >= bh:
                for t in cut_line_positions(bw, spacing_px):
                    x = int(x1 + t)
                    self._dashed_line(img, (x, int(y1)), (x, int(y2)), color)
            else:
                for t in cut_line_positions(bh, spacing_px):
                    y = int(y1 + t)
                    self._dashed_line(img, (int(x1), y), (int(x2), y), color)
            return

        n = config.CUT_LINE_COUNT
        if bw >= bh:
            for i in range(1, n + 1):
                t = i / (n + 1)
                x = int(x1 + bw * t)
                self._dashed_line(img, (x, int(y1)), (x, int(y2)), color)
        else:
            for i in range(1, n + 1):
                t = i / (n + 1)
                y = int(y1 + bh * t)
                self._dashed_line(img, (int(x1), y), (int(x2), y), color)

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

    def _draw_checkbox(
        self,
        img: np.ndarray,
        x: int,
        y: int,
        size: int,
        confirmed: bool,
        color: Tuple[int, int, int],
    ) -> None:
        x2, y2 = x + size, y + size
        cv2.rectangle(img, (x, y), (x2, y2), color, 2)
        if confirmed:
            # Check mark
            p1 = (x + 3, y + size // 2)
            p2 = (x + size // 2 - 1, y + size - 4)
            p3 = (x + size - 3, y + 3)
            cv2.line(img, p1, p2, color, 2)
            cv2.line(img, p2, p3, color, 2)

    def _draw_ingredient_checklist(
        self,
        img: np.ndarray,
        ingredients: Sequence[Dict[str, Any]],
    ) -> None:
        """Top-right checklist: [□] label — pending bright / confirmed green+tick."""
        if not ingredients:
            return

        h, w = img.shape[:2]
        pad = 10
        row_h = 34
        box = 18
        title_h = 28
        panel_w = 220
        panel_h = title_h + pad + len(ingredients) * row_h + pad
        x0 = max(10, w - panel_w - 10)
        y0 = 10  # top-right corner

        overlay = img.copy()
        cv2.rectangle(overlay, (x0, y0), (x0 + panel_w, y0 + panel_h), _COLOR_PANEL, -1)
        cv2.addWeighted(overlay, 0.72, img, 0.28, 0, img)
        cv2.rectangle(img, (x0, y0), (x0 + panel_w, y0 + panel_h), (80, 80, 80), 1)

        text_items: List[Tuple[str, Tuple[int, int], Tuple[int, int, int], int]] = [
            ("食材確認", (x0 + pad, y0 + 22), (255, 209, 102), 20)
        ]
        for i, row in enumerate(ingredients):
            label = str(row.get("label") or row.get("id") or "?")
            confirmed = bool(row.get("confirmed"))
            color = _COLOR_CONFIRMED if confirmed else _COLOR_PENDING
            cy = y0 + title_h + pad + i * row_h
            self._draw_checkbox(img, x0 + pad, cy + 4, box, confirmed, color)
            text_items.append((label, (x0 + pad + box + 10, cy + box), color, 22))
        draw_texts_bgr(img, text_items)

    def _draw_hud(
        self,
        img: np.ndarray,
        instruction: str,
        step_label: str,
        timer_remaining: float,
        hold_progress: Optional[float],
        *,
        scale_hint: str = "",
    ) -> None:
        h, w = img.shape[:2]
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (w, 78), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)

        title = step_label or "KITCHEN"
        cv2.putText(img, title, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 209, 102), 2)
        if instruction:
            text = instruction if len(instruction) < 90 else instruction[:87] + "..."
            # Prefer CJK-capable draw for recipe instructions
            draw_text_bgr(img, text, (12, 58), (240, 240, 240), font_size=18)

        help_y = h - 16
        help_text = "[R] restart  [C] scale  [N/Space] next  [Q/ESC] quit"
        if scale_hint:
            help_text = f"{scale_hint}  |  {help_text}"
        cv2.putText(
            img,
            help_text,
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
                (12, h - 48),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 200, 255),
                2,
            )

        if hold_progress is not None and hold_progress > 0:
            bar_w = int((w - 24) * min(1.0, hold_progress))
            cv2.rectangle(img, (12, h - 40), (12 + bar_w, h - 28), (0, 200, 255), -1)
