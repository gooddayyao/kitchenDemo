"""Unit checks for recipe parsing (no live server required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.recipe_parser import parse_recipe_text, _normalize_recipe


def test_rule_based_timer_and_cut_lines() -> None:
    text = """### 食譜名稱：測試菜
#### 材料：
- [ ] 洋蔥 1 顆 (切丁)
#### 步驟：
- [ ] **步驟 1：** 洋蔥切丁
- [ ] **步驟 2：** 炒香洋蔥 2 分鐘
"""
    recipe = parse_recipe_text(text)
    assert recipe["title"] == "測試菜"
    assert len(recipe["steps"]) >= 2
    step1 = recipe["steps"][0]
    assert step1["guidance_type"] == "cut_lines"
    assert step1["guide_lines"] is not None
    step2 = recipe["steps"][1]
    assert step2["timer_seconds"] == 120
    assert step2["zone"] == "stove"
    assert step2["completion"] in ("timer", "vision_heuristic")


def test_normalize_fills_missing_fields() -> None:
    raw = {
        "title": "補齊測試",
        "ingredients": [{"name": "蛋", "quantity": "1"}],
        "steps": [{"instruction": "煎蛋直到金黃"}],
    }
    recipe = _normalize_recipe(raw)
    assert recipe["id"]
    assert recipe["zones"]["stove"]["label"] == "爐灶區"
    step = recipe["steps"][0]
    assert step["zone"] in ("stove", "prep", "cutting_board")
    assert step["completion"] in ("timer", "manual_confirm", "marker_detect", "vision_heuristic")
    assert step["guidance_type"] in ("text", "cut_lines", "confirm_prep")


def test_marker_completion_inference() -> None:
    recipe = parse_recipe_text(
        "### 食譜名稱：標記\n#### 材料：\n- [ ] 貼紙 1\n#### 步驟：\n- [ ] **步驟 1：** 完成後請勾選標記"
    )
    assert recipe["steps"][0]["completion"] == "marker_detect"


def main() -> int:
    test_rule_based_timer_and_cut_lines()
    test_normalize_fills_missing_fields()
    test_marker_completion_inference()
    print("PARSER TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
