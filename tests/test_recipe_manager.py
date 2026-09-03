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
        self.assertEqual(self.mgr.resolve_yolo_class("cucumber"), "cucumber")
        self.assertEqual(self.mgr.resolve_yolo_class("garlic"), "garlic")

    def test_manual_confirm(self) -> None:
        self.mgr.confirm()
        self.assertEqual(self.mgr.statuses[0], StepStatus.DONE)
        self.assertEqual(self.mgr.current_index, 1)

    def test_count_trigger_hold(self) -> None:
        # Need >3 cucumbers for hold
        pieces = [
            Detection("cucumber", 0.9, 10 + i * 20, 10, 25 + i * 20, 40) for i in range(4)
        ]
        t0 = time.monotonic()
        self.mgr.update(pieces, 200, 200, now=t0)
        self.assertEqual(self.mgr.statuses[0], StepStatus.ACTIVE)
        self.mgr.update(pieces, 200, 200, now=t0 + 2.1)
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

    def test_import_cooking_recipe_cucumber_demo(self) -> None:
        from src import config

        mgr = RecipeManager.from_path(config.RECIPES_DIR / "cucumber.json")
        self.assertEqual(mgr.name, "小黃瓜切片 Demo")
        self.assertEqual(mgr.required_ingredients()[0]["id"], "cucumber")
        self.assertEqual(mgr.current_step()["trigger_condition"], "target_present")
        self.assertEqual(mgr.current_step()["target_ingredient"], "cucumber")
        cucumber = [Detection("cucumber", 0.9, 10, 10, 40, 40)]
        t0 = time.monotonic()
        mgr.update(cucumber, 200, 200, now=t0)
        mgr.update(cucumber, 200, 200, now=t0 + 1.0)
        self.assertEqual(mgr.recipe.get("_source"), "web_adapter")
        self.assertEqual(mgr.current_index, 1)
        self.assertTrue(mgr.ingredient_checklist()[0]["confirmed"])
        self.assertTrue(mgr.current_step()["guide_lines"])
        self.assertEqual(mgr.current_step().get("cut_spacing_mm"), 10)
        self.assertEqual(mgr.ingredient_checklist()[0]["children"][0]["label"], "切成 1cm 薄片")

    def test_cucumber_demo_flow(self) -> None:
        """Wait for cucumber → cut step with confirm_on_complete → checklist ticks."""
        mgr = RecipeManager(
            recipe={
                "recipe_name": "demo",
                "ingredients": [{"id": "cucumber", "label": "小黃瓜"}],
                "steps": [
                    {
                        "step_id": 0,
                        "instruction": "place cucumber",
                        "target_ingredient": "cucumber",
                        "trigger_condition": "target_present",
                        "guide_lines": False,
                    },
                    {
                        "step_id": 1,
                        "instruction": "cut 1cm",
                        "target_ingredient": "cucumber",
                        "trigger_condition": "manual_confirm",
                        "guide_lines": True,
                        "cut_spacing_mm": 10,
                        "confirm_on_complete": True,
                        "checklist_label": "切成 1cm 薄片",
                    },
                ],
            }
        )
        self.assertFalse(mgr.ingredient_checklist()[0]["confirmed"])
        self.assertEqual(mgr.ingredient_checklist()[0]["children"], [])
        cucumber = [Detection("cucumber", 0.9, 10, 10, 40, 40)]
        t0 = time.monotonic()
        mgr.update(cucumber, 200, 200, now=t0)
        self.assertEqual(mgr.current_index, 0)
        self.assertFalse(mgr.ingredient_checklist()[0]["confirmed"])
        mgr.update(cucumber, 200, 200, now=t0 + 1.0)
        self.assertEqual(mgr.statuses[0], StepStatus.DONE)
        self.assertEqual(mgr.current_index, 1)
        self.assertTrue(mgr.current_step()["guide_lines"])
        self.assertTrue(mgr.ingredient_checklist()[0]["confirmed"])
        children = mgr.ingredient_checklist()[0]["children"]
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]["label"], "切成 1cm 薄片")
        self.assertFalse(children[0]["confirmed"])
        self.assertTrue(children[0]["active"])
        mgr.confirm()
        self.assertTrue(mgr.is_finished())
        self.assertTrue(mgr.ingredient_checklist()[0]["confirmed"])
        self.assertTrue(mgr.ingredient_checklist()[0]["children"][0]["confirmed"])
        self.assertEqual(mgr.message, "Demo 完成！")
        mgr.reset()
        self.assertEqual(mgr.current_index, 0)
        self.assertFalse(mgr.is_finished())
        self.assertFalse(mgr.ingredient_checklist()[0]["confirmed"])
        self.assertEqual(mgr.ingredient_checklist()[0]["children"], [])


if __name__ == "__main__":
    unittest.main()
