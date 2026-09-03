"""Gemini keyframe seeding: identify ingredients + approximate bboxes."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import cv2
import numpy as np

from src.ingredient_catalog import all_items, item_by_id, label_for
from src.recipe_manager import Detection


@dataclass
class SeedObject:
    """One ingredient proposal from Gemini (normalized 0–1 box)."""

    ingredient_id: str
    label: str
    conf: float
    x: float
    y: float
    w: float
    h: float

    def to_detection(self, frame_w: int, frame_h: int) -> Detection:
        x1 = float(np.clip(self.x, 0.0, 1.0) * frame_w)
        y1 = float(np.clip(self.y, 0.0, 1.0) * frame_h)
        x2 = float(np.clip(self.x + self.w, 0.0, 1.0) * frame_w)
        y2 = float(np.clip(self.y + self.h, 0.0, 1.0) * frame_h)
        if x2 <= x1 + 2:
            x2 = min(float(frame_w), x1 + 20)
        if y2 <= y1 + 2:
            y2 = min(float(frame_h), y1 + 20)
        return Detection(
            name=self.ingredient_id,
            conf=float(self.conf),
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
        )


def frame_to_jpeg_b64(frame: np.ndarray, max_side: int = 960, quality: int = 80) -> str:
    """Encode BGR frame as base64 JPEG (optionally downscaled for API speed)."""
    img = frame
    h, w = img.shape[:2]
    scale = 1.0
    if max(h, w) > max_side:
        scale = max_side / float(max(h, w))
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError("Failed to encode frame as JPEG")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _catalog_hint() -> str:
    lines = []
    for item in all_items():
        lines.append(f"- {item.get('id')}: {item.get('label')}")
    return "\n".join(lines[:80])


def _normalize_id(raw: str) -> str:
    text = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "小黃瓜": "cucumber",
        "黄瓜": "cucumber",
        "黃瓜": "cucumber",
        "cucumber": "cucumber",
        "garlic": "garlic",
        "大蒜": "garlic",
        "mouse": "mouse",
        "滑鼠": "mouse",
        "banana": "banana",
        "apple": "apple",
        "tomato": "tomato",
        "onion": "onion",
        "egg": "egg",
        "knife": "knife",
        "bowl": "bowl",
    }
    if text in aliases:
        return aliases[text]
    # Chinese label → id via catalog
    for item in all_items():
        label = str(item.get("label") or "")
        if label and (label in raw or raw in label):
            return str(item["id"])
        if str(item.get("id")) == text:
            return str(item["id"])
    # strip unknown punctuation
    text = re.sub(r"[^a-z0-9_\u4e00-\u9fff]", "", text)
    if item_by_id(text):
        return text
    return text or "unknown"


def parse_gemini_objects(payload: Dict[str, Any]) -> List[SeedObject]:
    """Parse Gemini JSON into SeedObject list (tolerant of common shapes)."""
    raw_list = payload.get("objects") or payload.get("ingredients") or payload.get("items") or []
    if isinstance(payload, list):
        raw_list = payload
    out: List[SeedObject] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        name_raw = item.get("id") or item.get("name") or item.get("ingredient") or item.get("label") or ""
        ingredient_id = _normalize_id(str(name_raw))
        label = str(item.get("label") or label_for(ingredient_id) or name_raw or ingredient_id)
        conf = float(item.get("confidence") or item.get("conf") or 0.7)

        bbox = item.get("bbox") or item.get("box") or item.get("rect")
        x = y = w = h = None
        if isinstance(bbox, dict):
            x = bbox.get("x", bbox.get("xmin", bbox.get("left")))
            y = bbox.get("y", bbox.get("ymin", bbox.get("top")))
            w = bbox.get("w", bbox.get("width"))
            h = bbox.get("h", bbox.get("height"))
            if w is None and bbox.get("xmax") is not None and x is not None:
                w = float(bbox["xmax"]) - float(x)
            if h is None and bbox.get("ymax") is not None and y is not None:
                h = float(bbox["ymax"]) - float(y)
        elif isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            x, y, w, h = bbox[0], bbox[1], bbox[2], bbox[3]
            # If looks like xyxy in 0–1
            if float(w) > float(x) and float(h) > float(y) and float(w) <= 1.5 and float(h) <= 1.5:
                w = float(w) - float(x)
                h = float(h) - float(y)

        if x is None or y is None or w is None or h is None:
            continue
        x_f, y_f, w_f, h_f = float(x), float(y), float(w), float(h)
        # If pixel-like numbers slipped in, caller should pass frame size; clamp later.
        if w_f <= 0 or h_f <= 0:
            continue
        # Normalize if values look like pixels (>1.5)
        # Leave as-is here; clamp_seed_to_unit handles >1 by assuming already unit if all <=1.
        out.append(
            SeedObject(
                ingredient_id=ingredient_id,
                label=label,
                conf=max(0.0, min(1.0, conf)),
                x=x_f,
                y=y_f,
                w=w_f,
                h=h_f,
            )
        )
    return out


def clamp_seeds_to_unit(seeds: Sequence[SeedObject], frame_w: int, frame_h: int) -> List[SeedObject]:
    """Convert pixel boxes to 0–1 if needed and clamp."""
    fixed: List[SeedObject] = []
    for s in seeds:
        x, y, w, h = s.x, s.y, s.w, s.h
        if max(x, y, w, h) > 1.5:
            x /= float(frame_w)
            y /= float(frame_h)
            w /= float(frame_w)
            h /= float(frame_h)
        x = float(np.clip(x, 0.0, 1.0))
        y = float(np.clip(y, 0.0, 1.0))
        w = float(np.clip(w, 0.01, 1.0 - x))
        h = float(np.clip(h, 0.01, 1.0 - y))
        fixed.append(
            SeedObject(
                ingredient_id=s.ingredient_id,
                label=s.label,
                conf=s.conf,
                x=x,
                y=y,
                w=w,
                h=h,
            )
        )
    return fixed


def build_seed_prompt(
    *,
    focus_ids: Optional[Sequence[str]] = None,
    hint: Optional[str] = None,
) -> str:
    focus = ""
    if focus_ids:
        labels = [f"{i}({label_for(i)})" for i in focus_ids]
        focus = f"优先寻找并框出这些目标：{', '.join(labels)}。\n"
    extra = f"场景提示：{hint}\n" if hint else ""
    return f"""你是厨房台面俯拍视觉助手。请分析这张照片，找出可见的食材/厨具。
{focus}{extra}
可用的 ingredient id 参考（尽量使用这些 id）：
{_catalog_hint()}

规则：
1. 只返回 JSON，不要 markdown。
2. bbox 使用归一化坐标 0~1：x,y 为左上角，w,h 为宽高。
3. 不确定就不要编造；可省略。
4. 同一物体只报一次。

JSON 格式：
{{
  "objects": [
    {{
      "id": "cucumber",
      "label": "小黃瓜",
      "confidence": 0.85,
      "bbox": {{"x": 0.2, "y": 0.3, "w": 0.4, "h": 0.2}}
    }}
  ]
}}
"""


def seed_from_frame(
    frame: np.ndarray,
    *,
    focus_ids: Optional[Sequence[str]] = None,
    hint: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[SeedObject]:
    """Call Gemini on a keyframe and return normalized seed objects."""
    from services.gemini_client import analyze_image_json, get_api_key

    if not (api_key or get_api_key()):
        raise RuntimeError("GEMINI_API_KEY is not configured")

    h, w = frame.shape[:2]
    b64 = frame_to_jpeg_b64(frame)
    prompt = build_seed_prompt(focus_ids=focus_ids, hint=hint)
    payload = analyze_image_json(b64, prompt, api_key=api_key)
    seeds = parse_gemini_objects(payload)
    return clamp_seeds_to_unit(seeds, w, h)
