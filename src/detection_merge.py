"""Merge / conflict rules between color produce detectors and YOLO."""

from __future__ import annotations

from typing import Iterable, List, Sequence, Set

import cv2
import numpy as np

from src.recipe_manager import Detection

# Elongated utensils YOLO often confuses with cucumber / carrot.
_UTENSIL_LIKE: Set[str] = {"knife", "fork", "spoon", "scissors"}


def _iou(a: Detection, b: Detection) -> float:
    x1 = max(a.x1, b.x1)
    y1 = max(a.y1, b.y1)
    x2 = min(a.x2, b.x2)
    y2 = min(a.y2, b.y2)
    iw = max(0.0, x2 - x1)
    ih = max(0.0, y2 - y1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1.0, (a.x2 - a.x1) * (a.y2 - a.y1))
    area_b = max(1.0, (b.x2 - b.x1) * (b.y2 - b.y1))
    return inter / (area_a + area_b - inter)


def _green_ratio(frame: np.ndarray, det: Detection) -> float:
    h, w = frame.shape[:2]
    x1 = max(0, int(det.x1))
    y1 = max(0, int(det.y1))
    x2 = min(w, int(det.x2))
    y2 = min(h, int(det.y2))
    if x2 <= x1 or y2 <= y1:
        return 0.0
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (25, 40, 40), (95, 255, 255))
    return float(cv2.countNonZero(mask)) / float(mask.size)


def merge_produce_and_yolo(
    frame: np.ndarray,
    produce: Sequence[Detection],
    yolo: Sequence[Detection],
    *,
    iou_suppress: float = 0.12,
    utensil_green_reject: float = 0.22,
) -> List[Detection]:
    """
    Prefer cucumber/color produce over YOLO utensils that overlap or look green.

    Fixes common case: elongated cucumber classified as COCO "knife".
    """
    produce_list = list(produce)
    kept: List[Detection] = []

    for det in yolo:
        # Drop utensils that overlap a produce detection.
        if any(_iou(det, p) >= iou_suppress for p in produce_list):
            continue
        # Drop utensils whose box is mostly green (misread produce).
        if det.name in _UTENSIL_LIKE and _green_ratio(frame, det) >= utensil_green_reject:
            continue
        kept.append(det)

    return produce_list + kept
