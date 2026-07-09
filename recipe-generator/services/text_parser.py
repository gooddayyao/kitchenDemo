"""Parse recipe from plain text via Gemini."""

from __future__ import annotations

from services.gemini_client import generate_json, get_api_key
from services.recipe_normalizer import normalize_recipe

RECIPE_JSON_SCHEMA_HINT = """{
  "id": "string",
  "title": "string",
  "ingredients": [{"name": "string", "quantity": "string", "prep": "string|null"}],
  "zones": {
    "cutting_board": {"label": "砧板區", "x": 0.08, "y": 0.18, "w": 0.38, "h": 0.52},
    "stove": {"label": "爐灶區", "x": 0.52, "y": 0.12, "w": 0.38, "h": 0.58},
    "prep": {"label": "備料區", "x": 0.08, "y": 0.74, "w": 0.82, "h": 0.18}
  },
  "steps": [{
    "step": 1,
    "title": "string",
    "instruction": "string",
    "zone": "cutting_board|stove|prep",
    "guidance_type": "text|cut_lines|confirm_prep",
    "timer_seconds": 0,
    "completion": "timer|manual_confirm|marker_detect|vision_heuristic",
    "guide_lines": null,
    "substeps": [{"id": "1.1", "instruction": "string", "timer_seconds": 0, "completion": "manual_confirm"}]
  }]
}"""


def build_text_prompt(text: str) -> str:
    return f"""Parse this Chinese recipe into JSON matching this schema:
{RECIPE_JSON_SCHEMA_HINT}

Rules:
- Use completion=timer when instruction has a clear duration
- Use completion=vision_heuristic for stove stir/fry/sear observations
- Use guide_lines when guidance_type is cut_lines
- Return ONLY valid JSON, no markdown

Recipe text:
{text}
"""


def parse_recipe_from_text(text: str) -> dict:
    if not get_api_key():
        raise RuntimeError("GEMINI_API_KEY is not configured")

    data = generate_json(build_text_prompt(text))
    return normalize_recipe(data)
