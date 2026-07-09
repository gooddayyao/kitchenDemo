"""Parse recipe from video file or URL via Gemini (skeleton with upload flow)."""

from __future__ import annotations

from services.gemini_client import generate_with_file, get_api_key
from services.gemini_files import max_video_bytes, upload_video, wait_until_active
from services.recipe_normalizer import normalize_recipe
from services.text_parser import RECIPE_JSON_SCHEMA_HINT

ALLOWED_VIDEO_MIME = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/mpeg",
}


def build_video_prompt(title_hint: str | None = None, language: str = "zh-TW") -> str:
    hint = f"\nTitle hint: {title_hint}" if title_hint else ""
    return f"""你是料理食譜結構化助手。請分析這支烹飪教學影片（語音與畫面），輸出符合下列 schema 的 JSON：
{RECIPE_JSON_SCHEMA_HINT}

規則：
- 語言：{language}
- 從影片辨識材料名稱、份量、備料方式與步驟順序
- 有明確時間（分鐘/秒）→ 填 timer_seconds，completion=timer
- 炒菜/煎鍋/翻炒等 → completion=vision_heuristic
- 切菜/切片 → zone=cutting_board, guidance_type=cut_lines
- 不確定時 completion=manual_confirm，不要亂猜
- 只回傳 JSON，不要 markdown{hint}
"""


def parse_recipe_from_video(
    content: bytes,
    mime_type: str,
    title_hint: str | None = None,
    language: str = "zh-TW",
) -> dict:
    if not get_api_key():
        raise RuntimeError("GEMINI_API_KEY is not configured")

    if mime_type not in ALLOWED_VIDEO_MIME:
        raise ValueError(f"Unsupported video type: {mime_type}")

    if len(content) > max_video_bytes():
        raise ValueError(f"Video exceeds MAX_VIDEO_MB limit ({len(content)} bytes)")

    uploaded = upload_video(content, mime_type)
    file_name = uploaded.get("name")
    file_uri = uploaded.get("uri")
    if not file_name or not file_uri:
        raise RuntimeError(f"Unexpected upload response: {uploaded}")

    wait_until_active(file_name)
    prompt = build_video_prompt(title_hint=title_hint, language=language)
    data = generate_with_file(file_uri, mime_type, prompt)
    return normalize_recipe(data)


def parse_recipe_from_url(url: str, language: str = "zh-TW") -> dict:
    """Parse recipe from a public video URL (e.g. YouTube). Not implemented yet."""
    raise NotImplementedError(
        "URL parsing is not implemented yet. Use /v1/parse-recipe/video to upload a file."
    )
