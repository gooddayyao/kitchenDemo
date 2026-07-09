"""Minimal Gemini REST client for text/JSON generation."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import requests

DEFAULT_MODEL = "gemini-2.0-flash"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def get_api_key() -> Optional[str]:
    return os.getenv("GEMINI_API_KEY")


def get_model() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL)


def _extract_json(text: str) -> Dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def generate_json(
    prompt: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    key = api_key or get_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    model_name = model or get_model()
    url = API_URL.format(model=model_name) + f"?key={key}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=body, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _extract_json(text)


def generate_with_file(
    file_uri: str,
    mime_type: str,
    prompt: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate structured JSON from an uploaded Gemini file URI."""
    key = api_key or get_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    model_name = model or get_model()
    url = API_URL.format(model=model_name) + f"?key={key}"
    body = {
        "contents": [{
            "parts": [
                {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                {"text": prompt},
            ]
        }]
    }
    resp = requests.post(url, json=body, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _extract_json(text)
