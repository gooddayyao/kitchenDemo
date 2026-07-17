"""Common kitchen ingredient catalog (labels + how they can be detected)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src import config

CATALOG_PATH = config.DATA_DIR / "ingredient_catalog.json"


@lru_cache(maxsize=1)
def load_catalog() -> Dict[str, Any]:
    if not CATALOG_PATH.exists():
        return {"items": []}
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def all_items() -> List[Dict[str, Any]]:
    return list(load_catalog().get("items") or [])


def item_by_id(ing_id: str) -> Optional[Dict[str, Any]]:
    for item in all_items():
        if str(item.get("id")) == ing_id:
            return item
    return None


def label_for(name_or_id: str) -> str:
    """Chinese display label for catalog id or YOLO class name."""
    key = str(name_or_id or "").strip()
    if not key:
        return "?"
    item = item_by_id(key)
    if item:
        return str(item.get("label") or key)
    for item in all_items():
        if str(item.get("yolo") or "") == key:
            return str(item.get("label") or key)
        if str(item.get("id")) == key.replace(" ", "_"):
            return str(item.get("label") or key)
    return key


def detectable_items() -> List[Dict[str, Any]]:
    return [i for i in all_items() if i.get("detect") in ("yolo", "color_green")]


def yolo_class_names() -> List[str]:
    names: Set[str] = set()
    for item in all_items():
        if item.get("detect") == "yolo" and item.get("yolo"):
            names.add(str(item["yolo"]))
    return sorted(names)


def color_detect_ids() -> List[str]:
    return [str(i["id"]) for i in all_items() if i.get("detect") == "color_green"]


def remap_detection_name(yolo_name: str) -> str:
    """Map YOLO class string → catalog id when possible."""
    for item in all_items():
        if item.get("detect") == "yolo" and str(item.get("yolo")) == yolo_name:
            return str(item["id"])
    return yolo_name


def summarize_detectable() -> str:
    parts = []
    for item in detectable_items():
        parts.append(f"{item['label']}({item.get('detect')})")
    return ", ".join(parts)
