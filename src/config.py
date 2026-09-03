"""Runtime configuration for the CV (KITCHEN Phase 1) pipeline.

Adjustable values live in:
  - data/kitchen_recipe_schema.json  — CV 食譜欄位／trigger 架構
  - data/kitchen_detect_profile.json — YOLO 對應、確認物件、觸發門檻
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

# Repo roots
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RECIPES_DIR = DATA_DIR / "recipes"
KITCHEN_RECIPE_SCHEMA = DATA_DIR / "kitchen_recipe_schema.json"
KITCHEN_DETECT_PROFILE = DATA_DIR / "kitchen_detect_profile.json"
SCALE_CALIBRATION_PATH = DATA_DIR / "scale_calibration.json"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


_PROFILE = _load_json(KITCHEN_DETECT_PROFILE)

# Video / stream
DEFAULT_SOURCE = "0"  # webcam index, local file path, or RTSP/HTTP URL
RECONNECT_DELAY_SEC = 2.0
READ_FAIL_RECONNECT_AFTER = 15  # consecutive failed reads before reconnect
DRAIN_EXTRA_GRABS = 2  # non-threaded path: drop a few buffered frames per read

# YOLO / detect profile
YOLO_MODEL = str(_PROFILE.get("yolo_model", "yolov8n.pt"))
YOLO_CONF = float(_PROFILE.get("yolo_conf", 0.35))
YOLO_IOU = float(_PROFILE.get("yolo_iou", 0.45))
LOCK_CONF = float(_PROFILE.get("lock_conf", 0.7))
LOCK_LOST_SEC = float(_PROFILE.get("lock_lost_sec", 0.8))
POC_CLASS_MAP: Dict[str, str] = dict(
    _PROFILE.get("poc_class_map")
    or {
        "cucumber": "cucumber",
        "garlic": "garlic",
        "mouse": "mouse",
    }
)
CONFIRM_OBJECT_CLASS = str(_PROFILE.get("confirm_object_class", "mouse"))

_TRIGGERS = dict(_PROFILE.get("triggers") or {})
COUNT_HOLD_SEC = float(_TRIGGERS.get("count_hold_sec", 2.0))
COUNT_FROM = int(_TRIGGERS.get("count_from", 1))
COUNT_TO = int(_TRIGGERS.get("count_to", 3))
DROPZONE_HOLD_SEC = float(_TRIGGERS.get("dropzone_hold_sec", 2.0))
PRESENT_HOLD_SEC = float(_TRIGGERS.get("present_hold_sec", 0.8))

DEFAULT_DROPZONE = dict(
    _PROFILE.get("default_dropzone")
    or {"x": 0.72, "y": 0.08, "w": 0.22, "h": 0.22, "label": "暫存確認區"}
)

_OVERLAY = dict(_PROFILE.get("overlay") or {})
CUT_LINE_COUNT = int(_OVERLAY.get("cut_line_count", 3))

_default_recipe_name = str(_PROFILE.get("default_recipe", "cucumber.json"))
DEFAULT_CV_RECIPE = RECIPES_DIR / _default_recipe_name

# Display
WINDOW_NAME = "KITCHEN AR Preview"

# Valid trigger_condition values (kept in sync with kitchen_recipe_schema.json)
VALID_TRIGGERS = frozenset(
    {
        "target_count_increase",
        "target_present",
        "enter_dropzone",
        "timer",
        "manual_confirm",
    }
)