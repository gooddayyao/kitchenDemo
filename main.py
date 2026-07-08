from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services.recipe_parser import list_recipe_ids, load_recipe, parse_recipe_text
from services.vision import analyze_frame, vision_backend_status

app = FastAPI(title="AI Cooking Assistant Projection Demo")

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
CALIBRATION_FILE = BASE_DIR / "data" / "calibration.json"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ParseRecipeRequest(BaseModel):
    text: str


class VisionAnalyzeRequest(BaseModel):
    image: str
    step_context: Optional[Dict[str, Any]] = None


class CalibrationData(BaseModel):
    corners: List[Dict[str, float]]
    zones: Optional[Dict[str, Any]] = None


@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    vision_status = vision_backend_status()
    return {
        "status": "ok",
        "phase": "2-5",
        "recipes": list_recipe_ids(),
        "gemini_configured": vision_status["gemini_configured"],
        "vision_mode": vision_status["mode"],
        "pillow_available": vision_status["pillow_available"],
    }


@app.get("/api/recipes")
async def get_recipes():
    recipes = []
    for recipe_id in list_recipe_ids():
        recipe = load_recipe(recipe_id)
        total_timer = sum(s.get("timer_seconds", 0) for s in recipe.get("steps", []))
        recipes.append({
            "id": recipe["id"],
            "title": recipe["title"],
            "step_count": len(recipe.get("steps", [])),
            "total_timer_seconds": total_timer,
        })
    return {"recipes": recipes}


@app.get("/api/recipes/{recipe_id}")
async def get_recipe(recipe_id: str):
    try:
        return load_recipe(recipe_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/parse-recipe")
async def parse_recipe(req: ParseRecipeRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Recipe text is required")
    return parse_recipe_text(req.text.strip())


@app.get("/api/calibration")
async def get_calibration():
    if CALIBRATION_FILE.exists():
        with CALIBRATION_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    return {"corners": [], "zones": None}


@app.post("/api/calibration")
async def save_calibration(data: CalibrationData):
    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = data.model_dump()
    with CALIBRATION_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return {"status": "saved", **payload}


@app.post("/api/vision/analyze")
async def vision_analyze(req: VisionAnalyzeRequest):
    return analyze_frame(req.image, req.step_context)
