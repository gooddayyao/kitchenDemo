"""Unit tests for RecipeManager (no YOLO / camera required)."""

from __future__ import annotations

import time
import unittest

from src.recipe_manager import Detection, RecipeManager, StepStatus


class RecipeManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mgr = RecipeManager(
            recipe={
                "recipe_name": "test",
                "current_step_index": 0,
                "dropzone": {"x": 0.5, "y": 0.0, "w": 0.5, "h": 0.5, "label": "dz"},
                "steps": [
                    {
                        "step_id": 0,
                        "instruction": "slice",
                        "target_ingredient": "cucumber",
                        "trigger_condition": "target_count_increase",
                        "guide_lines": True,
                    },
                    {
                        "step_id": 1,
                        "instruction": "drop",
                        "target_ingredient": "garlic",
                        "trigger_condition": "enter_dropzone",
                        "guide_lines": False,
                    },
                    {
                        "step_id": 2,
                        "instruction": "confirm with mouse",
                        "target_ingredient": None,
                        "trigger_condition": "manual_confirm",
                        "guide_lines": False,
                    },
                ],
            }
        )

    def test_poc_class_map(self) -> None:
        self.assertEqual(self.mgr.resolve_yolo_class("cucumber"), "banana")
        self.assertEqual(self.mgr.resolve_yolo_class("garlic"), "apple")

    def test_manual_confirm(self) -> None:
        self.mgr.confirm()
        self.assertEqual(self.mgr.statuses[0], StepStatus.DONE)
        self.assertEqual(self.mgr.current_index, 1)

    def test_count_trigger_hold(self) -> None:
        # Map cucumber → banana; need >3 bananas for hold
        bananas = [
            Detection("banana", 0.9, 10 + i * 20, 10, 25 + i * 20, 40) for i in range(4)
        ]
        t0 = time.monotonic()
        self.mgr.update(bananas, 200, 200, now=t0)
        self.assertEqual(self.mgr.statuses[0], StepStatus.ACTIVE)
        self.mgr.update(bananas, 200, 200, now=t0 + 2.1)
        self.assertEqual(self.mgr.statuses[0], StepStatus.DONE)

    def test_mouse_confirm_in_dropzone(self) -> None:
        self.mgr.confirm()  # finish step 0
        self.mgr.confirm()  # finish step 1
        self.assertEqual(self.mgr.current_index, 2)
        # dropzone is right half x>=0.5; place mouse inside
        mouse = [Detection("mouse", 0.9, 120, 20, 180, 80)]
        t0 = time.monotonic()
        self.mgr.update(mouse, 200, 200, now=t0)
        self.assertEqual(self.mgr.statuses[2], StepStatus.ACTIVE)
        self.mgr.update(mouse, 200, 200, now=t0 + 2.1)
        self.assertEqual(self.mgr.statuses[2], StepStatus.DONE)

    def test_web_adapter(self) -> None:
        mgr = RecipeManager.from_web_recipe(
            {
                "id": "steak",
                "title": "香煎牛排",
                "zones": {"prep": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "label": "備料"}},
                "steps": [
                    {
                        "step": 1,
                        "title": "準備",
                        "instruction": "擦乾",
                        "completion": "manual_confirm",
                        "timer_seconds": 0,
                        "guidance_type": "text",
                    }
                ],
            }
        )
        self.assertEqual(mgr.name, "香煎牛排")
        self.assertEqual(mgr.current_step()["trigger_condition"], "manual_confirm")


if __name__ == "__main__":
    unittest.main()
