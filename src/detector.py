"""YOLOv8 detector wrapper for kitchen AR preview."""

from __future__ import annotations

from typing import List, Optional, Sequence, Set

import numpy as np

from src.recipe_manager import Detection


class Detector:
    """Load ultralytics YOLOv8 and return named bounding boxes."""

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

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                cls_id = int(box.cls.item())
                name = self.class_names.get(cls_id, str(cls_id))
                if allow is not None and name not in allow:
                    continue
                conf = float(box.conf.item())
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                out.append(Detection(name=name, conf=conf, x1=x1, y1=y1, x2=x2, y2=y2))
        return out
