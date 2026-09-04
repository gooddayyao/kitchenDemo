"""OpenCV overlay: object silhouette, cut-lines, ingredient checklist."""

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

TOOLBAR_ACTIONS: Tuple[Tuple[str, str], ...] = (
    ("restart", "重新開始"),
    ("calibrate", "校正尺度"),
    ("toggle_camera", "隱藏相機"),
    ("next", "下一步"),
    ("quit", "離開"),
)
_BLANK_CAMERA_BGR = (28, 28, 28)
TOOLBAR_H = 52
HUD_BODY_H = 48
ERROR_BANNER_H = 40
TOP_CHROME_H = TOOLBAR_H + HUD_BODY_H

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


def _measure_text(text: str, font_size: int) -> Tuple[int, int]:
    font = _resolve_font(font_size)
    if font is not None:
        try:
            bbox = font.getbbox(text)
            return max(1, int(bbox[2] - bbox[0])), max(1, int(bbox[3] - bbox[1]))
        except Exception:
            pass
    return max(1, len(text) * max(8, font_size // 2)), font_size


def layout_toolbar(frame_w: int, *, show_camera: bool = True) -> List[Dict[str, Any]]:
    """Hit-testable top-row buttons. frame_w reserved for future wrapping."""
    _ = frame_w
    x = 10
    y = 8
    height = 36
    gap = 8
    buttons: List[Dict[str, Any]] = []
    for action, label in TOOLBAR_ACTIONS:
        if action == "toggle_camera":
            label = "隱藏相機" if show_camera else "顯示相機"
        tw, _th = _measure_text(label, 18)
        width = max(100, tw + 28)
        buttons.append(
            {"id": action, "label": label, "x": x, "y": y, "w": width, "h": height}
        )
        x += width + gap
    return buttons


def hit_toolbar(buttons: Sequence[Dict[str, Any]], x: int, y: int) -> Optional[str]:
    for btn in buttons:
        if btn["x"] <= x <= btn["x"] + btn["w"] and btn["y"] <= y <= btn["y"] + btn["h"]:
            return str(btn["id"])
    return None


def _hue_sat_mask(hsv: np.ndarray, hue: int, dh: int = 16) -> np.ndarray:
    h0 = int((hue - dh) % 180)
    h1 = int((hue + dh) % 180)
    lo_s, lo_v = 35, 35
    if h0 <= h1:
        return cv2.inRange(hsv, (h0, lo_s, lo_v), (h1, 255, 255))
    a = cv2.inRange(hsv, (h0, lo_s, lo_v), (180, 255, 255))
    b = cv2.inRange(hsv, (0, lo_s, lo_v), (h1, 255, 255))
    return cv2.bitwise_or(a, b)


def _smooth_closed_contour(contour: np.ndarray, window: int = 7) -> np.ndarray:
    pts = contour.reshape(-1, 2).astype(np.float32)
    n = len(pts)
    if n < 5:
        return contour
    w = max(3, window | 1)
    if w >= n:
        w = n if n % 2 == 1 else n - 1
    if w < 3:
        return contour
    pad = w // 2
    extended = np.concatenate([pts[-pad:], pts, pts[:pad]], axis=0)
    kernel = np.ones((w, 1), dtype=np.float32) / float(w)
    sm = cv2.filter2D(extended, -1, kernel, borderType=cv2.BORDER_CONSTANT)
    return sm[pad : pad + n].reshape(-1, 1, 2)


def _grabcut_mask(roi: np.ndarray) -> Optional[np.ndarray]:
    rh, rw = roi.shape[:2]
    if rh < 24 or rw < 24:
        return None
    mask = np.zeros((rh, rw), np.uint8)
    inset = 2
    rect = (inset, inset, rw - 2 * inset, rh - 2 * inset)
    if rect[2] <= 2 or rect[3] <= 2:
        return None
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(roi, mask, rect, bgd, fgd, 1, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        return None
    binary = np.where(
        (mask == int(cv2.GC_FGD)) | (mask == int(cv2.GC_PR_FGD)),
        255,
        0,
    ).astype(np.uint8)
    if int(np.count_nonzero(binary)) < 40:
        return None
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    return cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)


def _align_closed(prev: np.ndarray, nxt: np.ndarray) -> np.ndarray:
    """Roll / reverse a resampled loop so vertices correspond to the previous outline."""
    if prev.shape != nxt.shape or len(nxt) < 3:
        return nxt
    best = nxt
    best_d = float("inf")
    for candidate in (nxt, nxt[::-1].copy()):
        for k in range(len(candidate)):
            rolled = np.roll(candidate, k, axis=0)
            d = float(np.sum((prev - rolled) ** 2))
            if d < best_d:
                best_d = d
                best = rolled
    return best


def _resample_closed(pts: np.ndarray, n: int = 48) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
    if len(pts) < 3:
        return pts
    closed = np.vstack([pts, pts[0]])
    segs = np.diff(closed, axis=0)
    dist = np.sqrt((segs ** 2).sum(axis=1))
    total = float(dist.sum())
    if total < 1.0:
        return np.repeat(pts[:1], n, axis=0)
    cum = np.concatenate([[0.0], np.cumsum(dist)])
    samples = np.linspace(0.0, total, n, endpoint=False)
    out = np.empty((n, 2), dtype=np.float32)
    j = 0
    for i, s in enumerate(samples):
        while j + 1 < len(cum) and cum[j + 1] < s:
            j += 1
        span = cum[j + 1] - cum[j]
        t = 0.0 if span < 1e-6 else (s - cum[j]) / span
        out[i] = closed[j] * (1.0 - t) + closed[j + 1] * t
    return out


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


class OverlayRenderer:
    def __init__(self) -> None:
        self.hover_id: Optional[str] = None
        self.show_camera: bool = True
        self._toolbar: List[Dict[str, Any]] = []
        self._frame_size: Tuple[int, int] = (0, 0)
        self._outline_pts: Dict[str, np.ndarray] = {}
        self._top_chrome_h = TOP_CHROME_H

    def clear(self) -> None:
        self._outline_pts.clear()

    def toggle_camera(self) -> bool:
        """Show/hide live camera pixels; overlays stay. Returns new show_camera state."""
        self.show_camera = not self.show_camera
        return self.show_camera

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
        error_message: str = "",
    ) -> np.ndarray:
        # Keep the real frame for silhouette extraction even when camera is hidden.
        if self.show_camera:
            out = frame.copy()
        else:
            out = np.full(frame.shape, _BLANK_CAMERA_BGR, dtype=np.uint8)
        self._top_chrome_h = TOP_CHROME_H + (ERROR_BANNER_H if error_message else 0)
        drawables = [
            d for d in detections if d.name != config.CONFIRM_OBJECT_CLASS
        ]

        # Dropzone confirm region is intentionally not drawn (was upper-right green box).
        _ = dropzone  # kept for API compatibility / future use

        live_keys = {self._outline_key(d) for d in drawables}
        for name in list(self._outline_pts):
            if name not in live_keys:
                del self._outline_pts[name]

        for det in drawables:
            is_target = False
            if highlight_class is None:
                is_target = True
            else:
                is_target = det.name == highlight_class
                if not is_target:
                    is_target = label_for(det.name) == label_for(highlight_class)
            nice = label_for(det.name)
            color = det.glow_color or (0, 220, 90)
            self._draw_object_outline(out, frame, det, color)
            key = self._outline_key(det)
            pts = self._outline_pts.get(key)
            if pts is not None and len(pts):
                top = pts[int(np.argmin(pts[:, 1]))]
                tw, _th = _measure_text(nice, 18)
                lx = int(round(float(top[0]))) - tw // 2
                ly = max(self._top_chrome_h + 18, int(round(float(top[1]))) - 6)
            else:
                lx = int(round(det.x1))
                ly = max(self._top_chrome_h + 18, int(round(det.y1)) - 8)
            draw_text_bgr(out, nice, (lx, ly), color, font_size=18)
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
            error_message=error_message,
        )
        if ingredients:
            self._draw_ingredient_checklist(out, list(ingredients))
        return out

    def set_hover(self, x: int, y: int) -> None:
        self.hover_id = hit_toolbar(self._toolbar, x, y)

    def hit_action(self, x: int, y: int) -> Optional[str]:
        return hit_toolbar(self._toolbar, x, y)

    def _outline_key(self, det: Detection) -> str:
        if det.track_id:
            return str(det.track_id)
        return f"{det.name}:{int(det.cx) // 12}:{int(det.cy) // 12}"

    def _draw_object_outline(
        self,
        img: np.ndarray,
        source: np.ndarray,
        det: Detection,
        color: Tuple[int, int, int],
    ) -> None:
        """Stroke the object's silhouette instead of a glow ellipse."""
        contour = self._extract_outline(source, det)
        key = self._outline_key(det)
        prev = self._outline_pts.get(key)
        if contour is None:
            contour = prev
        if contour is None:
            self._draw_ellipse_outline(img, det, color)
            return
        if prev is not None and prev.shape == contour.shape:
            contour = (0.62 * prev + 0.38 * _align_closed(prev, contour)).astype(np.float32)
        self._outline_pts[key] = contour
        pts = np.round(contour).astype(np.int32)
        cv2.drawContours(img, [pts], -1, (0, 0, 0), 5, lineType=cv2.LINE_AA)
        cv2.drawContours(img, [pts], -1, color, 3, lineType=cv2.LINE_AA)

    def _draw_ellipse_outline(
        self,
        img: np.ndarray,
        det: Detection,
        color: Tuple[int, int, int],
    ) -> None:
        cx = int(round((det.x1 + det.x2) * 0.5))
        cy = int(round((det.y1 + det.y2) * 0.5))
        ax = max(1, int(round((det.x2 - det.x1) * 0.5)))
        ay = max(1, int(round((det.y2 - det.y1) * 0.5)))
        cv2.ellipse(img, (cx, cy), (ax, ay), 0, 0, 360, (0, 0, 0), 4, lineType=cv2.LINE_AA)
        cv2.ellipse(img, (cx, cy), (ax, ay), 0, 0, 360, color, 2, lineType=cv2.LINE_AA)

    def _extract_outline(self, frame: np.ndarray, det: Detection) -> Optional[np.ndarray]:
        if det.contour is not None:
            pts = np.asarray(det.contour, dtype=np.float32).reshape(-1, 2)
            if len(pts) >= 5:
                return _resample_closed(pts, 48)

        h, w = frame.shape[:2]
        pad = 10
        x1 = max(0, int(np.floor(det.x1)) - pad)
        y1 = max(0, int(np.floor(det.y1)) - pad)
        x2 = min(w, int(np.ceil(det.x2)) + pad)
        y2 = min(h, int(np.ceil(det.y2)) + pad)
        if x2 - x1 < 12 or y2 - y1 < 12:
            return None
        roi = frame[y1:y2, x1:x2]
        mask = self._segment_roi(roi, det)
        if mask is None:
            return None
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            return None
        cnt = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(cnt))
        box_area = float((x2 - x1) * (y2 - y1))
        if area < box_area * 0.08 or area < 40:
            return None
        epsilon = 0.006 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        if len(approx) < 5:
            approx = cnt
        approx = _smooth_closed_contour(approx, window=7)
        pts = approx.reshape(-1, 2).astype(np.float32)
        pts[:, 0] += x1
        pts[:, 1] += y1
        return _resample_closed(pts, 48)

    def _segment_roi(self, roi: np.ndarray, det: Detection) -> Optional[np.ndarray]:
        blur = cv2.GaussianBlur(roi, (5, 5), 0)
        hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        keep = (sat >= 35) & (val >= 35) & (val <= 235)
        mask = None
        if int(np.count_nonzero(keep)) >= 24:
            h_med = int(np.median(hsv[:, :, 0][keep]))
            mask = _hue_sat_mask(hsv, h_med)
            if det.glow_color:
                glow = np.uint8([[det.glow_color]])
                glow_h = int(cv2.cvtColor(glow, cv2.COLOR_BGR2HSV)[0, 0, 0])
                mask = cv2.bitwise_or(mask, _hue_sat_mask(hsv, glow_h))
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            fill = float(np.count_nonzero(mask)) / float(mask.size)
            if fill >= 0.08:
                return mask
        grabbed = _grabcut_mask(roi)
        if grabbed is not None:
            return grabbed
        return mask if mask is not None and int(np.count_nonzero(mask)) >= 40 else None

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
        """Top-right tree: ingredient checkbox, then prep sub-items after it is found."""
        if not ingredients:
            return

        h, w = img.shape[:2]
        pad = 10
        row_h = 32
        child_h = 28
        box = 18
        child_box = 15
        title_h = 28
        panel_w = 268
        body_h = 0
        for row in ingredients:
            body_h += row_h
            body_h += child_h * len(row.get("children") or [])
        panel_h = title_h + pad + body_h + pad
        x0 = max(10, w - panel_w - 10)
        y0 = self._top_chrome_h + 8

        overlay = img.copy()
        cv2.rectangle(overlay, (x0, y0), (x0 + panel_w, y0 + panel_h), _COLOR_PANEL, -1)
        cv2.addWeighted(overlay, 0.72, img, 0.28, 0, img)
        cv2.rectangle(img, (x0, y0), (x0 + panel_w, y0 + panel_h), (80, 80, 80), 1)

        text_items: List[Tuple[str, Tuple[int, int], Tuple[int, int, int], int]] = [
            ("步驟 / 食材", (x0 + pad, y0 + 22), (255, 209, 102), 20)
        ]
        cy = y0 + title_h + pad
        for row in ingredients:
            confirmed = bool(row.get("confirmed"))
            active = bool(row.get("active"))
            if confirmed:
                color = _COLOR_CONFIRMED
            elif active:
                color = _COLOR_PENDING
            else:
                color = (160, 160, 160)
            label = str(row.get("label") or row.get("id") or "?")
            self._draw_checkbox(img, x0 + pad, cy + 4, box, confirmed, color)
            text_items.append((label, (x0 + pad + box + 10, cy + box), color, 22))
            cy += row_h
            for child in row.get("children") or []:
                ch_ok = bool(child.get("confirmed"))
                ch_active = bool(child.get("active"))
                if ch_ok:
                    ch_color = _COLOR_CONFIRMED
                elif ch_active:
                    ch_color = _COLOR_PENDING
                else:
                    ch_color = (150, 150, 150)
                indent = x0 + pad + 18
                self._draw_checkbox(img, indent, cy + 5, child_box, ch_ok, ch_color)
                ch_label = str(child.get("label") or "?")
                text_items.append(
                    (ch_label, (indent + child_box + 8, cy + child_box + 2), ch_color, 18)
                )
                cy += child_h
        draw_texts_bgr(img, text_items)

    def _draw_toolbar(self, img: np.ndarray, scale_hint: str) -> None:
        h, w = img.shape[:2]
        self._frame_size = (w, h)
        self._toolbar = layout_toolbar(w, show_camera=self.show_camera)
        texts: List[Tuple[str, Tuple[int, int], Tuple[int, int, int], int]] = []
        for btn in self._toolbar:
            hovered = self.hover_id == btn["id"]
            fill = (48, 48, 48)
            border = (150, 150, 150)
            label_color = (240, 240, 240)
            if btn["id"] == "next":
                border = (0, 200, 255)
            elif btn["id"] == "quit":
                border = (90, 90, 210)
            elif btn["id"] == "toggle_camera":
                border = (120, 180, 90) if self.show_camera else (90, 90, 120)
            if hovered:
                fill = (72, 72, 72)
                border = (255, 209, 102)
            x1, y1 = int(btn["x"]), int(btn["y"])
            x2, y2 = x1 + int(btn["w"]), y1 + int(btn["h"])
            cv2.rectangle(img, (x1, y1), (x2, y2), fill, -1)
            cv2.rectangle(img, (x1, y1), (x2, y2), border, 2)
            tw, _th = _measure_text(str(btn["label"]), 18)
            font = _resolve_font(18)
            ascent = 18
            if font is not None:
                try:
                    ascent, _ = font.getmetrics()
                except Exception:
                    pass
            tx = x1 + max(6, (int(btn["w"]) - tw) // 2)
            ty = y1 + (int(btn["h"]) + ascent) // 2
            texts.append((str(btn["label"]), (tx, ty), label_color, 18))

        if scale_hint:
            hint_w, _ = _measure_text(scale_hint, 16)
            last = self._toolbar[-1] if self._toolbar else None
            min_x = (last["x"] + last["w"] + 16) if last else 12
            hx = w - 12 - hint_w
            if hx >= min_x:
                texts.append((scale_hint, (hx, 8 + 24), (180, 180, 180), 16))
        draw_texts_bgr(img, texts)

    def _draw_hud(
        self,
        img: np.ndarray,
        instruction: str,
        step_label: str,
        timer_remaining: float,
        hold_progress: Optional[float],
        *,
        scale_hint: str = "",
        error_message: str = "",
    ) -> None:
        h, w = img.shape[:2]
        chrome_h = self._top_chrome_h
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (w, chrome_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)

        self._draw_toolbar(img, scale_hint)

        body_y = TOOLBAR_H
        if error_message:
            y2 = TOOLBAR_H + ERROR_BANNER_H
            cv2.rectangle(img, (0, TOOLBAR_H), (w, y2), (36, 36, 196), -1)
            text = error_message if len(error_message) < 92 else error_message[:89] + "..."
            draw_texts_bgr(img, [(text, (12, TOOLBAR_H + 28), (235, 235, 255), 17)])
            body_y = y2

        body_items: List[Tuple[str, Tuple[int, int], Tuple[int, int, int], int]] = []
        title = step_label or "KITCHEN"
        body_items.append((title, (12, body_y + 20), (255, 209, 102), 18))
        if instruction:
            text = instruction if len(instruction) < 90 else instruction[:87] + "..."
            body_items.append((text, (12, body_y + 42), (240, 240, 240), 18))
        draw_texts_bgr(img, body_items)

        help_y = h - 16
        help_text = "[G] Gemini  [R] restart  [C] scale  [N/Space] next  [Q/ESC] quit"
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
