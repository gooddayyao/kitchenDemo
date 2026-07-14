"""Recipe state machine for the CV mainline (KITCHEN Phase 1)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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

    def __post_init__(self) -> None:
        self.statuses = {
            int(step["step_id"]): StepStatus.PENDING for step in self.recipe["steps"]
        }
        start = int(self.recipe.get("current_step_index", 0))
        self._activate(start)

    @classmethod
    def from_path(cls, path: Path | str) -> "RecipeManager":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(recipe=data)

    @classmethod
    def from_web_recipe(cls, web: Dict[str, Any]) -> "RecipeManager":
        """Adapter: existing Web demo schema → KITCHEN CV format (no schema mutation)."""
        dropzone = dict(config.DEFAULT_DROPZONE)
        zones = web.get("zones") or {}
        if "prep" in zones:
            z = zones["prep"]
            dropzone = {
                "x": float(z.get("x", dropzone["x"])),
                "y": float(z.get("y", dropzone["y"])),
                "w": float(z.get("w", dropzone["w"])),
                "h": float(z.get("h", dropzone["h"])),
                "label": z.get("label", "備料區"),
            }

        steps: List[Dict[str, Any]] = []
        for raw in web.get("steps") or []:
            completion = raw.get("completion", "manual_confirm")
            if completion == "timer":
                trigger = "timer"
            elif completion == "manual_confirm":
                trigger = "manual_confirm"
            else:
                trigger = "manual_confirm"
            steps.append(
                {
                    "step_id": int(raw.get("step", len(steps) + 1)) - 1,
                    "instruction": raw.get("instruction") or raw.get("title") or "",
                    "target_ingredient": None,
                    "expected_status": completion,
                    "trigger_condition": trigger,
                    "timer_seconds": int(raw.get("timer_seconds") or 0),
                    "guide_lines": bool(raw.get("guide_lines"))
                    or raw.get("guidance_type") == "cut_lines",
                }
            )

        kitchen = {
            "recipe_name": web.get("title") or web.get("id") or "web-recipe",
            "current_step_index": 0,
            "steps": steps,
            "dropzone": dropzone,
            "_source": "web_adapter",
            "_web_id": web.get("id"),
        }
        return cls(recipe=kitchen)

    @property
    def name(self) -> str:
        return str(self.recipe.get("recipe_name", "recipe"))

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
        return config.POC_CLASS_MAP.get(target, target)

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

    def _complete(self, step_id: int) -> None:
        self.statuses[step_id] = StepStatus.DONE
        self._condition_since = None
        self._mouse_confirm_since = None
        self._timer_end_at = None
        self.timer_remaining = 0.0
        self.hold_progress = 0.0
        self.mouse_confirm_progress = 0.0
        next_index = self.current_index + 1
        if next_index >= len(self.recipe.get("steps") or []):
            self.message = "食譜完成！"
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
        target = self.resolve_yolo_class(step.get("target_ingredient"))
        matched = [d for d in detections if target and d.name == target]

        if trigger == "timer":
            if self._timer_end_at is not None:
                self.timer_remaining = max(0.0, self._timer_end_at - now)
                if now >= self._timer_end_at:
                    self._complete(sid)
            return

        if trigger == "manual_confirm":
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
