"""YOLOv8 detector wrapper for kitchen AR preview.

Supports both detection-only (yolov8n.pt) and segmentation (yolov8n-seg.pt)
models. When a seg model is loaded, Detection.contour is populated with the
instance mask polygon so the overlay renderer can draw precise outlines.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Set

import cv2
import numpy as np

from src.recipe_manager import Detection


class Detector:
    """Load ultralytics YOLOv8 and return named bounding boxes (+ optional masks)."""

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        conf: float = 0.35,
        iou: float = 0.45,
        device: Optional[str] = None,
    ) -> None:
        from ultralytics import YOLO  # lazy import — heavy

        self.model = YOLO(model_name)
        self.conf = conf
        self.iou = iou
        self.device = device
        self.is_seg = self.model.task == "segment"
        names = self.model.names
        if isinstance(names, dict):
            self.class_names = {int(k): str(v) for k, v in names.items()}
        else:
            self.class_names = {i: str(n) for i, n in enumerate(names)}

    def detect(
        self,
        frame: np.ndarray,
        class_filter: Optional[Sequence[str]] = None,
    ) -> List[Detection]:
        kwargs = {
            "conf": self.conf,
            "iou": self.iou,
            "verbose": False,
        }
        if self.device:
            kwargs["device"] = self.device

        results = self.model.predict(frame, **kwargs)
        allow: Optional[Set[str]] = set(class_filter) if class_filter else None
        out: List[Detection] = []
        h, w = frame.shape[:2]

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue

            masks_data = result.masks
            pending: List[tuple] = []

            for i, box in enumerate(boxes):
                cls_id = int(box.cls.item())
                name = self.class_names.get(cls_id, str(cls_id))
                if allow is not None and name not in allow:
                    continue
                conf = float(box.conf.item())
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                mask = None
                if masks_data is not None and i < len(masks_data):
                    mask = _mask_array(masks_data[i], h, w)
                pending.append((name, conf, x1, y1, x2, y2, mask))

            idx = [i for i, p in enumerate(pending) if p[6] is not None]
            vis_list = visible_masks([pending[i][6] for i in idx], frame) if idx else []
            vis_by_i = {idx[k]: vis_list[k] for k in range(len(idx))}
            for i, (name, conf, x1, y1, x2, y2, _) in enumerate(pending):
                contour = None
                vis = vis_by_i.get(i)
                if vis is not None and int(vis.sum()) >= 80:
                    ys, xs = np.where(vis > 0)
                    x1, x2 = float(xs.min()), float(xs.max())
                    y1, y2 = float(ys.min()), float(ys.max())
                    contour = _binary_to_contour(vis)
                out.append(Detection(
                    name=name, conf=conf,
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    contour=contour,
                ))
        return out


def _mask_array(mask_obj: object, frame_h: int, frame_w: int) -> Optional[np.ndarray]:
    mask = mask_obj.data.cpu().numpy().squeeze()
    if mask.ndim != 2:
        return None
    resized = cv2.resize(mask, (frame_w, frame_h), interpolation=cv2.INTER_LINEAR)
    return (resized > 0.5).astype(np.uint8)


def _binary_to_contour(binary: np.ndarray) -> Optional[np.ndarray]:
    contours, _ = cv2.findContours(binary * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


def visible_masks(masks: List[np.ndarray], img: np.ndarray, min_overlap: int = 40) -> List[np.ndarray]:
    """Keep only visible pixels: overlap belongs to the slice on top, not the one underneath."""
    bins = [m.astype(np.uint8).copy() for m in masks]
    n = len(bins)
    for _ in range(4):
        changed = False
        for i in range(n):
            for j in range(i + 1, n):
                if int(bins[i].sum()) == 0 or int(bins[j].sum()) == 0:
                    continue
                overlap = bins[i] * bins[j]
                if int(overlap.sum()) < min_overlap:
                    continue
                top = _top_index(bins[i], bins[j], overlap, img)
                bot = j if top == 0 else i
                top_i = i if top == 0 else j
                clipped = bins[bot] * (1 - bins[top_i])
                if int(clipped.sum()) != int(bins[bot].sum()):
                    bins[bot] = clipped
                    changed = True
        if not changed:
            break
    return bins


def _top_index(a: np.ndarray, b: np.ndarray, overlap: np.ndarray, img: np.ndarray) -> int:
    """Return 0 if A is on top of B, else 1. Overlap color should match the uncovered part of the top slice."""
    a_only = a * (1 - b)
    b_only = b * (1 - a)
    a_n, b_n = int(a_only.sum()), int(b_only.sum())
    a_tot, b_tot = int(a.sum()), int(b.sum())
    if a_n < max(20, 0.15 * a_tot) and a_tot <= b_tot:
        return 0
    if b_n < max(20, 0.15 * b_tot) and b_tot <= a_tot:
        return 1
    if a_n < 20 or b_n < 20:
        return 0 if a_tot <= b_tot else 1
    mean_ov = img[overlap.astype(bool)].reshape(-1, 3).mean(axis=0)
    mean_a = img[a_only.astype(bool)].reshape(-1, 3).mean(axis=0)
    mean_b = img[b_only.astype(bool)].reshape(-1, 3).mean(axis=0)
    da = float(np.linalg.norm(mean_ov - mean_a))
    db = float(np.linalg.norm(mean_ov - mean_b))
    return 0 if da <= db else 1
