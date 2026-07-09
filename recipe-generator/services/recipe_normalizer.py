"""Normalize Gemini output to CookingRecipe schema."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_ZONES = {
    "cutting_board": {"label": "砧板區", "x": 0.08, "y": 0.18, "w": 0.38, "h": 0.52},
    "stove": {"label": "爐灶區", "x": 0.52, "y": 0.12, "w": 0.38, "h": 0.58},
    "prep": {"label": "備料區", "x": 0.08, "y": 0.74, "w": 0.82, "h": 0.18},
}

VALID_ZONES = set(DEFAULT_ZONES.keys())
VALID_GUIDANCE = {"text", "cut_lines", "confirm_prep"}
VALID_COMPLETION = {"timer", "manual_confirm", "marker_detect", "vision_heuristic"}


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


def normalize_recipe(raw: dict[str, Any]) -> dict[str, Any]:
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
