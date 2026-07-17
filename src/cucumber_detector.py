"""Heuristic cucumber detector (green elongated blob) for live camera demos.

YOLOv8n COCO has no "cucumber" class; this fills the gap for the kitchen demo.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

from src.recipe_manager import Detection


def detect_cucumber(
    frame: np.ndarray,
    *,
    min_area_ratio: float = 0.01,
    max_area_ratio: float = 0.55,
    min_aspect: float = 1.6,
) -> List[Detection]:
    """
    Find the best green elongated region and label it as cucumber.

    Returns 0 or 1 detection with contour outline when possible.
    """
    if frame is None or frame.size == 0:
        return []

    h, w = frame.shape[:2]
    frame_area = float(h * w)
    min_area = frame_area * min_area_ratio
    max_area = frame_area * max_area_ratio

    # Slight blur reduces phone-stream noise
    blur = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)

    # Broad green range (covers light/dark cucumber skin under kitchen light)
    mask1 = cv2.inRange(hsv, (35, 40, 40), (95, 255, 255))
    # Some cucumbers lean yellow-green
    mask2 = cv2.inRange(hsv, (25, 50, 50), (40, 255, 255))
    mask = cv2.bitwise_or(mask1, mask2)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: Optional[Tuple[float, Detection]] = None

    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        if area < min_area or area > max_area:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw < 8 or bh < 8:
            continue
        aspect = max(bw, bh) / float(min(bw, bh))
        if aspect < min_aspect:
            continue

        # Prefer larger + more elongated
        score = area * aspect
        fill = area / float(bw * bh)
        if fill < 0.25:
            continue

        # Keep a smoother outline: light simplify + moving-average (reduces jagged folds)
        epsilon = 0.004 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        if len(approx) < 3:
            approx = cnt
        approx = _smooth_contour_points(approx, window=9)

        det = Detection(
            name="cucumber",
            conf=float(min(0.99, 0.50 + 0.4 * fill)),
            x1=float(x),
            y1=float(y),
            x2=float(x + bw),
            y2=float(y + bh),
            contour=approx,
        )
        if best is None or score > best[0]:
            best = (score, det)

    return [best[1]] if best else []


def _smooth_contour_points(contour: np.ndarray, window: int = 9) -> np.ndarray:
    """Circular moving-average on contour vertices for softer edges."""
    pts = contour.reshape(-1, 2).astype(np.float32)
    n = len(pts)
    if n < 5:
        return contour
    w = max(3, window | 1)  # odd
    if w >= n:
        w = n if n % 2 == 1 else n - 1
    if w < 3:
        return contour
    pad = w // 2
    # wrap for closed contour
    extended = np.concatenate([pts[-pad:], pts, pts[:pad]], axis=0)
    kernel = np.ones((w, 1), dtype=np.float32) / float(w)
    sm = cv2.filter2D(extended, -1, kernel, borderType=cv2.BORDER_CONSTANT)
    smoothed = sm[pad : pad + n]
    return smoothed.reshape(-1, 1, 2).astype(np.int32)
