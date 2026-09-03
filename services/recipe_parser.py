from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from services.gemini_client import generate_json, get_api_key

RECIPES_DIR = Path(__file__).resolve().parent.parent / "data" / "recipes"

DEFAULT_ZONES = {
    "cutting_board": {"label": "砧板區", "x": 0.08, "y": 0.18, "w": 0.38, "h": 0.52},
    "stove": {"label": "爐灶區", "x": 0.52, "y": 0.12, "w": 0.38, "h": 0.58},
    "prep": {"label": "備料區", "x": 0.08, "y": 0.74, "w": 0.82, "h": 0.18},
}

VALID_ZONES = set(DEFAULT_ZONES.keys())
VALID_GUIDANCE = {"text", "cut_lines", "confirm_prep"}
VALID_COMPLETION = {"timer", "manual_confirm", "marker_detect", "vision_heuristic"}


def list_recipe_ids() -> list[str]:
    if not RECIPES_DIR.exists():
        return []
    return sorted(p.stem for p in RECIPES_DIR.glob("*.json") if not p.stem.endswith("_cv"))


def load_recipe(recipe_id: str) -> dict[str, Any]:
    path = RECIPES_DIR / f"{recipe_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Recipe not found: {recipe_id}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _infer_zone(instruction: str) -> str:
    if any(k in instruction for k in ("切", "片", "丁", "砧板", "靜置")):
        return "cutting_board"
    if any(k in instruction for k in ("鍋", "煎", "炒", "煮", "滾", "爐", "翻面", "淋油")):
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


def _infer_completion(instruction: str, timer_seconds: int, guidance: str, zone: str) -> str:
    text = instruction
    if any(k in text for k in ("標記", "勾選", "打勾", "checkbox", "✓", "✔")):
        return "marker_detect"
    if timer_seconds > 0:
        # Timed stove actions can still use vision after / alongside the timer.
        if zone == "stove" and any(k in text for k in ("炒", "翻炒", "煎", "翻面", "冒煙", "活動")):
            if "直到" in text or "炒香" in text or "翻面" in text:
                return "vision_heuristic"
        return "timer"
    if zone == "stove" and any(k in text for k in ("炒", "煎", "翻", "煮", "鍋")):
        return "vision_heuristic"
    if guidance == "confirm_prep":
        return "manual_confirm"
    return "manual_confirm"


def _default_guide_lines(guidance: str) -> dict[str, Any] | None:
    if guidance != "cut_lines":
        return None
    return {
        "orientation": "grid",
        "spacing_px": 36,
        "count": 4,
        "label": "切配參考線",
    }


def _normalize_recipe(raw: dict[str, Any]) -> dict[str, Any]:
    title = str(raw.get("title") or "自訂食譜").strip()
    recipe_id = str(raw.get("id") or "").strip()
    if not recipe_id:
        recipe_id = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title).strip("-").lower() or "custom"

    zones = raw.get("zones") if isinstance(raw.get("zones"), dict) else {}
    merged_zones = {**DEFAULT_ZONES, **zones}

    ingredients: list[dict[str, Any]] = []
    for item in raw.get("ingredients") or []:
        if not isinstance(item, dict):
            continue
        ingredients.append({
            "name": str(item.get("name") or "").strip() or "材料",
            "quantity": str(item.get("quantity") or "").strip(),
            "prep": item.get("prep"),
        })

    steps: list[dict[str, Any]] = []
    for idx, step in enumerate(raw.get("steps") or [], start=1):
        if not isinstance(step, dict):
            continue
        instruction = str(step.get("instruction") or "").strip() or f"步驟 {idx}"
        title_s = str(step.get("title") or f"步驟 {idx}").strip()
        zone = str(step.get("zone") or _infer_zone(instruction))
        if zone not in VALID_ZONES:
            zone = _infer_zone(instruction)

        guidance = str(step.get("guidance_type") or _infer_guidance(instruction))
        if guidance not in VALID_GUIDANCE:
            guidance = _infer_guidance(instruction)

        try:
            timer_seconds = int(step.get("timer_seconds", _infer_timer_seconds(instruction)))
        except (TypeError, ValueError):
            timer_seconds = _infer_timer_seconds(instruction)
        timer_seconds = max(0, timer_seconds)

        completion = str(
            step.get("completion")
            or _infer_completion(instruction, timer_seconds, guidance, zone)
        )
        if completion not in VALID_COMPLETION:
            completion = _infer_completion(instruction, timer_seconds, guidance, zone)

        guide_lines = step.get("guide_lines")
        if guidance == "cut_lines" and not guide_lines:
            guide_lines = _default_guide_lines(guidance)
        if guidance != "cut_lines":
            guide_lines = None

        substeps = []
        for sub in step.get("substeps") or []:
            if not isinstance(sub, dict):
                continue
            substeps.append({
                "id": str(sub.get("id") or ""),
                "instruction": str(sub.get("instruction") or "").strip(),
                "timer_seconds": int(sub.get("timer_seconds") or 0),
                "completion": str(sub.get("completion") or "manual_confirm"),
            })

        steps.append({
            "step": int(step.get("step") or idx),
            "title": title_s,
            "instruction": instruction,
            "zone": zone,
            "guidance_type": guidance,
            "timer_seconds": timer_seconds,
            "completion": completion,
            "guide_lines": guide_lines,
            **({"substeps": substeps} if substeps else {}),
        })

    if not steps:
        steps = [{
            "step": 1,
            "title": "步驟 1",
            "instruction": title,
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
        "zones": merged_zones,
        "steps": steps,
    }


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
        if re.match(r"^#*\s*材料", stripped) or stripped in ("材料：", "材料:", "#### 材料：", "### 材料："):
            in_ingredients = True
            in_steps = False
            continue
        if re.match(r"^#*\s*步驟", stripped) or stripped.startswith("#### 步驟") or stripped.startswith("### 步驟"):
            in_ingredients = False
            in_steps = True
            continue

        # Avoid treating "- [ ] **步驟 N：** ..." as a section header
        if not stripped.startswith("-") and ("材料" in stripped[:6] or stripped.rstrip("：:") == "材料"):
            in_ingredients = True
            in_steps = False
            continue
        if not stripped.startswith("-") and ("步驟" in stripped[:6] or stripped.rstrip("：:") == "步驟"):
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
            completion = _infer_completion(instruction, timer_seconds, guidance, zone)
            step = {
                "step": step_num,
                "title": f"步驟 {step_num}",
                "instruction": instruction,
                "zone": zone,
                "guidance_type": guidance,
                "timer_seconds": timer_seconds,
                "completion": completion,
                "guide_lines": _default_guide_lines(guidance),
            }
            steps.append(step)

    return _normalize_recipe({
        "id": recipe_id,
        "title": title,
        "ingredients": ingredients,
        "zones": DEFAULT_ZONES,
        "steps": steps or [{
            "step": 1,
            "title": "步驟 1",
            "instruction": text[:200],
            "zone": "prep",
            "guidance_type": "text",
            "timer_seconds": 0,
            "completion": "manual_confirm",
            "guide_lines": None,
        }],
    })


def parse_recipe_text(text: str) -> dict[str, Any]:
    api_key = get_api_key()
    if api_key:
        try:
            return _parse_with_gemini(text, api_key)
        except Exception:
            pass
    return _rule_based_parse(text)


def _parse_with_gemini(text: str, api_key: str) -> dict[str, Any]:
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
    "guide_lines": null or {{"orientation": "horizontal|vertical|grid", "spacing_px": 36, "count": 4, "label": "string"}},
    "substeps": [{{"id": "1.1", "instruction": "string", "timer_seconds": 0, "completion": "manual_confirm"}}]
  }}]
}}

Rules:
- Use completion=timer when instruction has a clear duration and no visual condition
- Use completion=vision_heuristic for stove stir/fry/sear observations
- Use completion=marker_detect only when the user marks a checkbox/marker
- Use guide_lines when guidance_type is cut_lines

Recipe text:
{text}

Return ONLY valid JSON, no markdown."""

    data = generate_json(prompt, api_key=api_key)
    return _normalize_recipe(data)
