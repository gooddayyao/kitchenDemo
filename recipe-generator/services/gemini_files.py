"""Gemini File API helpers for video upload (skeleton)."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import requests

from services.gemini_client import get_api_key

FILES_UPLOAD_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"
FILES_GET_URL = "https://generativelanguage.googleapis.com/v1beta/{name}"


def upload_video(content: bytes, mime_type: str, display_name: str = "recipe-video") -> Dict[str, Any]:
    """
    Upload video bytes via Gemini File API.

    Returns file metadata including `uri` and `name` for generateContent.
    """
    key = get_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    headers = {
        "X-Goog-Upload-Protocol": "multipart",
    }
    metadata = {"file": {"display_name": display_name}}
    files = {
        "metadata": (None, str(metadata).replace("'", '"'), "application/json"),
        "file": (display_name, content, mime_type),
    }
    resp = requests.post(
        FILES_UPLOAD_URL + f"?key={key}",
        headers=headers,
        files=files,
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json().get("file", resp.json())


def wait_until_active(
    file_name: str,
    timeout_sec: float = 120,
    poll_interval_sec: float = 2.0,
) -> Dict[str, Any]:
    """Poll file state until ACTIVE or FAILED."""
    key = get_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    deadline = time.time() + timeout_sec
    url = FILES_GET_URL.format(name=file_name) + f"?key={key}"

    while time.time() < deadline:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        state = data.get("state", "PROCESSING")
        if state == "ACTIVE":
            return data
        if state == "FAILED":
            raise RuntimeError(f"Gemini file processing failed: {data}")
        time.sleep(poll_interval_sec)

    raise TimeoutError(f"Gemini file not ready within {timeout_sec}s: {file_name}")


def max_video_bytes() -> int:
    mb = int(os.getenv("MAX_VIDEO_MB", "100"))
    return mb * 1024 * 1024
