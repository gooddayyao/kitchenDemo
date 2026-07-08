"""Minimal Gemini REST client (works without latest google-generativeai SDK)."""

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


def _extract_json(text: str) -> Dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def generate_json(prompt: str, api_key: Optional[str] = None, model: str = DEFAULT_MODEL) -> Dict[str, Any]:
    key = api_key or get_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    url = API_URL.format(model=model) + f"?key={key}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=body, timeout=45)
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _extract_json(text)


def analyze_image_json(
    image_b64: str,
    prompt: str,
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    key = api_key or get_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    raw = image_b64.split(",", 1)[-1]
    mime = "image/jpeg"
    if image_b64.startswith("data:image/png"):
        mime = "image/png"

    url = API_URL.format(model=model) + f"?key={key}"
    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": raw}},
            ]
        }]
    }
    resp = requests.post(url, json=body, timeout=45)
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _extract_json(text)
