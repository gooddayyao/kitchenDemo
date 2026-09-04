"""Recipe state machine for the CV mainline (KITCHEN Phase 1)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src import config


class StepStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    AWAITING_CONFIRM = "awaiting_confirm"
    DONE = "done"


@dataclass
class Detection:
    name: str
    conf: float
    x1: float
    y1: float
    x2: float
    y2: float
    # Optional outline (Nx1x2 or Nx2 int/float). When set, overlay draws contour instead of box.
    contour: Optional[Any] = None
    locked: bool = False
    glow_color: Optional[Tuple[int, int, int]] = None
    track_id: Optional[str] = None

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    def intersects_rect(self, rect: Dict[str, float], frame_w: int, frame_h: int) -> bool:
        rx1 = rect["x"] * frame_w
        ry1 = rect["y"] * frame_h
        rx2 = (rect["x"] + rect["w"]) * frame_w
        ry2 = (rect["y"] + rect["h"]) * frame_h
        return not (self.x2 < rx1 or self.x1 > rx2 or self.y2 < ry1 or self.y1 > ry2)


@dataclass
class RecipeManager:
    recipe: Dict[str, Any]
    current_index: int = 0
    statuses: Dict[int, StepStatus] = field(default_factory=dict)
    timer_remaining: float = 0.0
    _timer_end_at: Optional[float] = None
    _condition_since: Optional[float] = None
    _mouse_confirm_since: Optional[float] = None
    message: str = ""
    hold_progress: float = 0.0  # 0..1 while a hold trigger is filling
    mouse_confirm_progress: float = 0.0  # 0..1 mouse-in-dropzone confirm
    ingredient_confirmed: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.statuses = {
            int(step["step_id"]): StepStatus.PENDING for step in self.recipe["steps"]
        }
        self.ingredient_confirmed = {ing["id"]: False for ing in self.required_ingredients()}
        start = int(self.recipe.get("current_step_index", 0))
        self._activate(start)

    @classmethod
    def from_path(cls, path: Path | str) -> "RecipeManager":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if cls._is_web_recipe(data):
            return cls.from_web_recipe(data)
        return cls(recipe=data)

    @staticmethod
    def _is_web_recipe(data: Dict[str, Any]) -> bool:
        """CookingRecipe uses steps[].step; KITCHEN CV uses steps[].step_id."""
        steps = data.get("steps") or []
        if not isinstance(steps, list) or not steps:
            return bool(data.get("title") and not data.get("recipe_name"))
        first = steps[0] if isinstance(steps[0], dict) else {}
        return "step" in first and "step_id" not in first

    @staticmethod
    def _web_ingredients(web: Dict[str, Any]) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []
        seen: set = set()
        try:
            from src.ingredient_catalog import id_for_label
        except Exception:
            id_for_label = lambda _n: None  # type: ignore

        for entry in web.get("ingredients") or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or entry.get("label") or "").strip()
            ing_id = str(entry.get("id") or "").strip() or (id_for_label(name) if name else None) or ""
            if not ing_id:
                continue
            if ing_id in seen:
                continue
            seen.add(ing_id)
            label = name
            if not label:
                try:
                    from src.ingredient_catalog import label_for

                    label = label_for(ing_id)
                except Exception:
                    label = ing_id
            items.append({"id": ing_id, "label": label or ing_id})
        return items

    @staticmethod
    def _trigger_from_web_step(raw: Dict[str, Any]) -> str:
        explicit = str(raw.get("trigger_condition") or "").strip()
        if explicit in config.VALID_TRIGGERS:
            return explicit
        completion = str(raw.get("completion") or "manual_confirm")
        if completion == "timer":
            return "timer"
        if completion == "marker_detect":
            return "enter_dropzone"
        if completion == "vision_heuristic":
            return "target_present" if raw.get("target_ingredient") else "manual_confirm"
        return "manual_confirm"

    @classmethod
    def from_web_recipe(cls, web: Dict[str, Any]) -> "RecipeManager":
        """Adapter: CookingRecipe (recipe-generator / Web) → KITCHEN CV runtime."""
        dropzone = dict(config.DEFAULT_DROPZONE)
        zones = web.get("zones") or {}
        zone_key = "prep" if "prep" in zones else ("cutting_board" if "cutting_board" in zones else None)
        if zone_key:
            z = zones[zone_key]
            dropzone = {
                "x": float(z.get("x", dropzone["x"])),
                "y": float(z.get("y", dropzone["y"])),
                "w": float(z.get("w", dropzone["w"])),
                "h": float(z.get("h", dropzone["h"])),
                "label": z.get("label", dropzone.get("label", "備料區")),
            }

        steps: List[Dict[str, Any]] = []
        for raw in web.get("steps") or []:
            if not isinstance(raw, dict):
                continue
            gl = raw.get("guide_lines")
            guide = gl is True or isinstance(gl, dict) or raw.get("guidance_type") == "cut_lines"
            target = raw.get("target_ingredient")
            cv_step: Dict[str, Any] = {
                "step_id": int(raw.get("step", len(steps) + 1)) - 1,
                "instruction": raw.get("instruction") or raw.get("title") or "",
                "target_ingredient": target,
                "expected_status": raw.get("expected_status") or raw.get("completion"),
                "trigger_condition": cls._trigger_from_web_step(raw),
                "timer_seconds": int(raw.get("timer_seconds") or 0),
                "guide_lines": bool(guide),
            }
            if raw.get("cut_spacing_mm") is not None:
                cv_step["cut_spacing_mm"] = float(raw["cut_spacing_mm"])
            if raw.get("checklist_label"):
                cv_step["checklist_label"] = str(raw["checklist_label"])
            elif raw.get("title") and cv_step["trigger_condition"] != "target_present":
                cv_step["checklist_label"] = str(raw["title"])
            if raw.get("confirm_on_complete"):
                cv_step["confirm_on_complete"] = True
            steps.append(cv_step)

        kitchen = {
            "recipe_name": web.get("title") or web.get("id") or "web-recipe",
            "current_step_index": 0,
            "ingredients": cls._web_ingredients(web),
            "steps": steps,
            "dropzone": dropzone,
            "_source": "web_adapter",
            "_web_id": web.get("id"),
        }
        return cls(recipe=kitchen)

    @property
    def name(self) -> str:
        return str(self.recipe.get("recipe_name", "recipe"))

    def required_ingredients(self) -> List[Dict[str, str]]:
        """Recipe ingredient checklist items: [{id, label}, ...]."""
        raw = self.recipe.get("ingredients")
        if isinstance(raw, list) and raw:
            items: List[Dict[str, str]] = []
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                ing_id = str(entry.get("id") or "").strip()
                if not ing_id:
                    continue
                label = str(entry.get("label") or ing_id).strip()
                items.append({"id": ing_id, "label": label})
            return items

        # Fallback: unique target_ingredient from steps
        seen: set = set()
        items = []
        for step in self.recipe.get("steps") or []:
            target = step.get("target_ingredient")
            if not target or target in seen:
                continue
            seen.add(target)
            items.append({"id": str(target), "label": str(target)})
        return items

    def ingredient_checklist(self) -> List[Dict[str, Any]]:
        """Checklist tree for overlay: ingredient row + visible prep sub-items."""
        steps = list(self.recipe.get("steps") or [])
        current = self.current_step()
        current_sid = int(current["step_id"]) if current else None
        rows: List[Dict[str, Any]] = []
        for ing in self.required_ingredients():
            ing_id = ing["id"]
            parent_confirmed = bool(self.ingredient_confirmed.get(ing_id, False))
            children: List[Dict[str, Any]] = []
            parent_active = False
            for step in steps:
                if str(step.get("target_ingredient") or "") != ing_id:
                    continue
                sid = int(step["step_id"])
                trigger = str(step.get("trigger_condition") or "")
                if trigger == "target_present":
                    parent_active = current_sid == sid
                    continue
                children.append(
                    {
                        "id": f"step:{sid}",
                        "step_id": sid,
                        "label": str(
                            step.get("checklist_label")
                            or step.get("instruction")
                            or f"步驟 {sid}"
                        ),
                        "confirmed": self.statuses.get(sid) == StepStatus.DONE,
                        "active": current_sid == sid,
                    }
                )
            rows.append(
                {
                    "id": ing_id,
                    "label": ing["label"],
                    "confirmed": parent_confirmed,
                    "active": parent_active and not parent_confirmed,
                    "children": children if parent_confirmed else [],
                }
            )
        return rows

    @property
    def dropzone(self) -> Dict[str, float]:
        dz = self.recipe.get("dropzone") or config.DEFAULT_DROPZONE
        return {
            "x": float(dz["x"]),
            "y": float(dz["y"]),
            "w": float(dz["w"]),
            "h": float(dz["h"]),
            "label": dz.get("label", "dropzone") if isinstance(dz, dict) else "dropzone",
        }

    def current_step(self) -> Optional[Dict[str, Any]]:
        steps = self.recipe.get("steps") or []
        if not steps or self.current_index < 0 or self.current_index >= len(steps):
            return None
        return steps[self.current_index]

    def status_of(self, step_id: int) -> StepStatus:
        return self.statuses.get(step_id, StepStatus.PENDING)

    def is_finished(self) -> bool:
        steps = self.recipe.get("steps") or []
        return bool(steps) and all(
            self.statuses.get(int(s["step_id"])) == StepStatus.DONE for s in steps
        )

    def resolve_yolo_class(self, target: Optional[str]) -> Optional[str]:
        if not target:
            return None
        mapped = config.POC_CLASS_MAP.get(target, target)
        # Recipe targets may use catalog ids; cucumber stays "cucumber" for color detector.
        return mapped

    def _match_detections(self, detections: Sequence[Detection], target: Optional[str]) -> List[Detection]:
        """Match detections by catalog id or YOLO class name."""
        if not target:
            return []
        yolo = self.resolve_yolo_class(target)
        aliases = {target, yolo}
        try:
            from src.ingredient_catalog import item_by_id

            item = item_by_id(str(target))
            if item and item.get("yolo"):
                aliases.add(str(item["yolo"]))
            if item and item.get("id"):
                aliases.add(str(item["id"]))
        except Exception:
            pass
        return [d for d in detections if d.name in aliases]

    def _activate(self, index: int) -> None:
        steps = self.recipe.get("steps") or []
        if index < 0 or index >= len(steps):
            self.message = "全部步驟完成"
            return
        self.current_index = index
        step = steps[index]
        sid = int(step["step_id"])
        self.statuses[sid] = StepStatus.ACTIVE
        self._condition_since = None
        self._mouse_confirm_since = None
        self.hold_progress = 0.0
        self.mouse_confirm_progress = 0.0
        self.message = step.get("instruction") or ""

        timer_sec = float(step.get("timer_seconds") or 0)
        if step.get("trigger_condition") == "timer" and timer_sec > 0:
            self.timer_remaining = timer_sec
            self._timer_end_at = time.monotonic() + timer_sec
        else:
            self.timer_remaining = 0.0
            self._timer_end_at = None

    def confirm(self) -> None:
        """Manual advance (Space / N)."""
        step = self.current_step()
        if not step:
            return
        self._complete(int(step["step_id"]))

    def reset(self) -> None:
        """Restart demo from the first step without reloading the recipe file."""
        self.statuses = {
            int(step["step_id"]): StepStatus.PENDING for step in self.recipe["steps"]
        }
        self.ingredient_confirmed = {ing["id"]: False for ing in self.required_ingredients()}
        self.timer_remaining = 0.0
        self._timer_end_at = None
        self._condition_since = None
        self._mouse_confirm_since = None
        self.hold_progress = 0.0
        self.mouse_confirm_progress = 0.0
        start = int(self.recipe.get("current_step_index", 0))
        self._activate(start)
        self.message = self.current_step().get("instruction") if self.current_step() else "重新開始"

    def _complete(self, step_id: int) -> None:
        step = None
        for s in self.recipe.get("steps") or []:
            if int(s["step_id"]) == step_id:
                step = s
                break

        self.statuses[step_id] = StepStatus.DONE
        self._condition_since = None
        self._mouse_confirm_since = None
        self._timer_end_at = None
        self.timer_remaining = 0.0
        self.hold_progress = 0.0
        self.mouse_confirm_progress = 0.0

        # Tick the ingredient when it is found; later steps become sub-items.
        if step:
            target = step.get("target_ingredient")
            trigger = str(step.get("trigger_condition") or "")
            if target and (trigger == "target_present" or step.get("confirm_on_complete")):
                self.ingredient_confirmed[str(target)] = True

        next_index = self.current_index + 1
        if next_index >= len(self.recipe.get("steps") or []):
            self.message = "Demo 完成！"
            return
        self._activate(next_index)

    def update(
        self,
        detections: Sequence[Detection],
        frame_w: int,
        frame_h: int,
        now: Optional[float] = None,
    ) -> None:
        """Evaluate trigger_condition against current detections."""
        now = now if now is not None else time.monotonic()
        step = self.current_step()
        if not step:
            return
        sid = int(step["step_id"])
        if self.statuses.get(sid) != StepStatus.ACTIVE:
            return

        # Universal visual confirm: physical mouse held inside dropzone.
        if self._try_mouse_confirm(detections, frame_w, frame_h, now, sid):
            return

        trigger = step.get("trigger_condition") or "manual_confirm"
        raw_target = step.get("target_ingredient")
        target = self.resolve_yolo_class(raw_target)
        matched = self._match_detections(detections, str(raw_target) if raw_target else None)

        if trigger == "timer":
            if self._timer_end_at is not None:
                self.timer_remaining = max(0.0, self._timer_end_at - now)
                if now >= self._timer_end_at:
                    self._complete(sid)
            return

        if trigger == "manual_confirm":
            return

        if trigger == "target_present":
            # Ingredient entered frame — advance after a short hold.
            held = len(matched) >= max(1, config.COUNT_FROM)
            self._update_hold(held, now, config.PRESENT_HOLD_SEC, sid)
            return

        if trigger == "target_count_increase":
            count = len(matched)
            # Hold when count exceeds COUNT_TO (e.g. sliced pieces).
            held = count > config.COUNT_TO
            self._update_hold(held, now, config.COUNT_HOLD_SEC, sid)
            return

        if trigger == "enter_dropzone":
            dz = self.dropzone
            inside = any(d.intersects_rect(dz, frame_w, frame_h) for d in matched) if matched else False
            if not target:
                inside = any(d.intersects_rect(dz, frame_w, frame_h) for d in detections)
            self._update_hold(inside, now, config.DROPZONE_HOLD_SEC, sid)
            return

    def _try_mouse_confirm(
        self,
        detections: Sequence[Detection],
        frame_w: int,
        frame_h: int,
        now: float,
        step_id: int,
    ) -> bool:
        """
        Detect COCO 'mouse' and complete the active step when it stays in the
        dropzone long enough. Returns True if step was completed.
        """
        mouse_name = config.CONFIRM_OBJECT_CLASS
        mice = [d for d in detections if d.name == mouse_name]
        inside = any(d.intersects_rect(self.dropzone, frame_w, frame_h) for d in mice)
        hold_sec = config.DROPZONE_HOLD_SEC

        if inside:
            if self._mouse_confirm_since is None:
                self._mouse_confirm_since = now
            elapsed = now - self._mouse_confirm_since
            self.mouse_confirm_progress = min(1.0, elapsed / hold_sec) if hold_sec > 0 else 1.0
            if elapsed >= hold_sec:
                self.message = "滑鼠確認完成"
                self._complete(step_id)
                return True
        else:
            self._mouse_confirm_since = None
            self.mouse_confirm_progress = 0.0
        return False

    def _update_hold(self, active: bool, now: float, hold_sec: float, step_id: int) -> None:
        if active:
            if self._condition_since is None:
                self._condition_since = now
            elapsed = now - self._condition_since
            self.hold_progress = min(1.0, elapsed / hold_sec) if hold_sec > 0 else 1.0
            if elapsed >= hold_sec:
                self._complete(step_id)
        else:
            self._condition_since = None
            self.hold_progress = 0.0
