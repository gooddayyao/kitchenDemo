from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from services.gemini_client import get_api_key
from services.text_parser import parse_recipe_from_text
from services.video_parser import parse_recipe_from_url, parse_recipe_from_video

APP_VERSION = "0.1.0"

app = FastAPI(
    title="Recipe Generator",
    description="Convert recipe videos, URLs, or text into CookingRecipe JSON.",
    version=APP_VERSION,
)


class ParseTextRequest(BaseModel):
    text: str = Field(..., min_length=1)


class ParseUrlRequest(BaseModel):
    url: str = Field(..., min_length=1)
    language: str = "zh-TW"


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "recipe-generator",
        "version": APP_VERSION,
        "gemini_configured": bool(get_api_key()),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    }


@app.post("/v1/parse-recipe/text")
async def parse_text(req: ParseTextRequest) -> Dict[str, Any]:
    try:
        return parse_recipe_from_text(req.text.strip())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Parse failed: {exc}") from exc


@app.post("/v1/parse-recipe/video")
async def parse_video(
    video: UploadFile = File(...),
    title_hint: Optional[str] = Form(None),
    language: str = Form("zh-TW"),
) -> Dict[str, Any]:
    if not video.content_type or not video.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="File must be a video")

    content = await video.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty video file")

    try:
        return parse_recipe_from_video(
            content,
            video.content_type,
            title_hint=title_hint,
            language=language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Video parse failed: {exc}") from exc


@app.post("/v1/parse-recipe/url")
async def parse_url(req: ParseUrlRequest) -> Dict[str, Any]:
    try:
        return parse_recipe_from_url(req.url.strip(), language=req.language)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"URL parse failed: {exc}") from exc
