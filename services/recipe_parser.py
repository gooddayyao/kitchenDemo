from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

RECIPES_DIR = Path(__file__).resolve().parent.parent / "data" / "recipes"

DEFAULT_ZONES = {
    "cutting_board": {"label": "砧板區", "x": 0.08, "y": 0.18, "w": 0.38, "h": 0.52},
    "stove": {"label": "爐灶區", "x": 0.52, "y": 0.12, "w": 0.38, "h": 0.58},
    "prep": {"label": "備料區", "x": 0.08, "y": 0.74, "w": 0.82, "h": 0.18},
}


def list_recipe_ids() -> list[str]:
    if not RECIPES_DIR.exists():
        return []
    return sorted(p.stem for p in RECIPES_DIR.glob("*.json"))


def load_recipe(recipe_id: str) -> dict[str, Any]:
    path = RECIPES_DIR / f"{recipe_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Recipe not found: {recipe_id}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _infer_zone(instruction: str) -> str:
    text = instruction.lower()
    if any(k in instruction for k in ("切", "片", "丁", "砧板", "靜置")):
        return "cutting_board"
    if any(k in instruction for k in ("鍋", "煎", "炒", "煮", "滾", "爐")):
        return "stove"
    return "prep"


def _infer_timer_seconds(instruction: str) -> int:
  patterns = [
      (r"(\d+)\s*分鐘", 60),
      (r"(\d+)\s*分", 60),
      (r"(\d+)\s*秒", 1),
  ]
  for pattern, mult in patterns:
      match = re.search(pattern, instruction)
      if match:
          return int(match.group(1)) * mult
  return 0


def _infer_guidance(instruction: str) -> str:
    if any(k in instruction for k in ("切", "片", "丁", "塊")):
        return "cut_lines"
    if any(k in instruction for k in ("備", "準備", "調味", "撒")):
        return "confirm_prep"
    return "text"


def _infer_completion(timer_seconds: int, guidance: str) -> str:
    if timer_seconds > 0:
        return "timer"
    if guidance == "confirm_prep":
        return "manual_confirm"
    return "manual_confirm"


def _rule_based_parse(text: str) -> dict[str, Any]:
    title_match = re.search(r"(?:食譜名稱|菜名)[：:]\s*(.+)", text)
    title = title_match.group(1).strip() if title_match else "自訂食譜"
    recipe_id = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title).strip("-").lower() or "custom"

    ingredients: list[dict[str, str | None]] = []
    in_ingredients = False
    in_steps = False
    steps: list[dict[str, Any]] = []
    step_num = 0

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "材料" in stripped:
            in_ingredients = True
            in_steps = False
            continue
        if "步驟" in stripped:
            in_ingredients = False
            in_steps = True
            continue

        if in_ingredients and stripped.startswith("- ["):
            item = re.sub(r"^-\s*\[\s*\]\s*", "", stripped)
            parts = item.split(" ", 1)
            name = parts[0]
            quantity = parts[1] if len(parts) > 1 else ""
            prep = None
            prep_match = re.search(r"\(([^)]+)\)", quantity)
            if prep_match:
                prep = prep_match.group(1)
            ingredients.append({"name": name, "quantity": quantity, "prep": prep})
            continue

        if in_steps and stripped.startswith("- ["):
            step_num += 1
            instruction = re.sub(r"^-\s*\[\s*\]\s*\*?\*?步驟\s*\d+[：:.]?\*?\*?\s*", "", stripped)
            instruction = re.sub(r"^\*+\s*", "", instruction)
            zone = _infer_zone(instruction)
            guidance = _infer_guidance(instruction)
            timer_seconds = _infer_timer_seconds(instruction)
            completion = _infer_completion(timer_seconds, guidance)
            step = {
                "step": step_num,
                "title": f"步驟 {step_num}",
                "instruction": instruction,
                "zone": zone,
                "guidance_type": guidance,
                "timer_seconds": timer_seconds,
                "completion": completion,
                "guide_lines": {
                    "orientation": "grid",
                    "spacing_px": 36,
                    "count": 4,
                    "label": "切配參考線",
                } if guidance == "cut_lines" else None,
            }
            steps.append(step)

    if not steps:
        steps = [{
            "step": 1,
            "title": "步驟 1",
            "instruction": text[:200],
            "zone": "prep",
            "guidance_type": "text",
            "timer_seconds": 0,
            "completion": "manual_confirm",
            "guide_lines": None,
        }]

    return {
        "id": recipe_id,
        "title": title,
        "ingredients": ingredients,
        "zones": DEFAULT_ZONES,
        "steps": steps,
    }


def parse_recipe_text(text: str) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            return _parse_with_gemini(text, api_key)
        except Exception:
            pass
    return _rule_based_parse(text)


def _parse_with_gemini(text: str, api_key: str) -> dict[str, Any]:
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    prompt = f"""Parse this Chinese recipe into JSON matching this schema:
{{
  "id": "string",
  "title": "string",
  "ingredients": [{{"name": "string", "quantity": "string", "prep": "string|null"}}],
  "zones": {{
    "cutting_board": {{"label": "砧板區", "x": 0.08, "y": 0.18, "w": 0.38, "h": 0.52}},
    "stove": {{"label": "爐灶區", "x": 0.52, "y": 0.12, "w": 0.38, "h": 0.58}},
    "prep": {{"label": "備料區", "x": 0.08, "y": 0.74, "w": 0.82, "h": 0.18}}
  }},
  "steps": [{{
    "step": 1,
    "title": "string",
    "instruction": "string",
    "zone": "cutting_board|stove|prep",
    "guidance_type": "text|cut_lines|confirm_prep",
    "timer_seconds": 0,
    "completion": "timer|manual_confirm|marker_detect|vision_heuristic",
    "guide_lines": null or {{"orientation": "horizontal|vertical|grid", "spacing_px": 36, "count": 4, "label": "string"}}
  }}]
}}

Recipe text:
{text}

Return ONLY valid JSON, no markdown."""

    response = model.generate_content(prompt)
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)
