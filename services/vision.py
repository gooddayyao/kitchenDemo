"""Semi-automatic vision heuristics and optional Gemini Vision analysis."""

from __future__ import annotations

import base64
import io
import os
from typing import Any, Dict, Optional

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from services.gemini_client import analyze_image_json, get_api_key

CONFIDENCE_THRESHOLD = 0.6


def analyze_frame(
    image_b64: str,
    step_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Analyze a camera frame and return detection result with confidence."""
    step_context = step_context or {}

    if not image_b64:
        return _result(False, 0.0, "no_frame", "未取得相機畫面", source="none")

    api_key = get_api_key()
    if api_key and step_context.get("completion") != "timer":
        try:
            gemini_result = _analyze_with_gemini(image_b64, step_context, api_key)
            heuristic = _analyze_heuristic(image_b64, step_context)
            return _merge_results(gemini_result, heuristic)
        except Exception as exc:
            heuristic = _analyze_heuristic(image_b64, step_context)
            heuristic["message"] = f"{heuristic['message']}（Gemini 暫不可用：{exc}）"
            heuristic["gemini_error"] = str(exc)
            return heuristic

    return _analyze_heuristic(image_b64, step_context)


def _analyze_with_gemini(
    image_b64: str,
    step_context: Dict[str, Any],
    api_key: str,
) -> Dict[str, Any]:
    zone = step_context.get("zone", "prep")
    completion = step_context.get("completion", "manual_confirm")
    instruction = step_context.get("instruction", "")
    title = step_context.get("title", "")
    motion_score = step_context.get("motion_score", 0.0)

    prompt = f"""你是廚房料理助手的視覺監控模組。請分析這張廚房相機畫面，判斷目前料理步驟是否完成。

目前步驟標題: {title}
步驟說明: {instruction}
工作區域 zone: {zone}
完成條件 completion: {completion}
前端 motion_score 參考: {motion_score}

請依 completion 類型判斷：
- manual_confirm / confirm_prep: 備料或操作是否看起來已完成
- vision_heuristic + stove: 鍋子是否有加熱/翻炒/冒煙等活動跡象
- marker_detect: 是否有完成標記、勾選記號或明顯標示

請只回傳 JSON：
{{"detected": true或false, "confidence": 0到1的小數, "message": "簡短繁體中文說明"}}

注意：
- 不確定時 confidence 必須 < 0.6
- 不要過度樂觀，避免誤判自動跳步
- 只回傳 JSON，不要 markdown"""

    data = analyze_image_json(image_b64, prompt, api_key=api_key)
    detected = bool(data.get("detected", False))
    confidence = float(data.get("confidence", 0.0))
    message = str(data.get("message", "Gemini 分析完成"))
    return _result(detected, confidence, "gemini_vision", message, source="gemini")


def _analyze_heuristic(image_b64: str, step_context: Dict[str, Any]) -> Dict[str, Any]:
    completion = step_context.get("completion", "manual_confirm")
    zone = step_context.get("zone", "prep")

    if not HAS_PIL:
        return _result(False, 0.3, "no_pillow", "視覺模組未就緒，請手動確認", source="heuristic")

    try:
        raw = image_b64.split(",", 1)[-1]
        img = Image.open(io.BytesIO(base64.b64decode(raw))).convert("L")
        pixels = list(img.getdata())
        if not pixels:
            return _result(False, 0.0, "empty_frame", "畫面為空", source="heuristic")

        avg = sum(pixels) / len(pixels)
        motion_score = step_context.get("motion_score", 0.0)

        if completion == "marker_detect":
            bright_ratio = sum(1 for p in pixels if p > 200) / len(pixels)
            detected = bright_ratio > 0.08
            confidence = min(0.95, 0.5 + bright_ratio * 3) if detected else 0.2
            return _result(
                detected,
                confidence,
                "marker",
                "偵測到標記" if detected else "尚未偵測到完成標記",
                source="heuristic",
            )

        if completion == "vision_heuristic" and zone == "stove":
            # Motion alone is noisy — keep confidence below auto-advance threshold
            # so the UI prompts for confirm unless Gemini is highly confident.
            active = motion_score > 0.02 or (120 < avg < 200 and motion_score > 0.005)
            confidence = 0.55 if active and motion_score > 0.03 else 0.3
            return _result(
                False,
                confidence,
                "pot_motion",
                "鍋子有活動跡象，請確認是否完成" if active else "鍋子狀態不明確，請確認",
                source="heuristic",
            )

        if completion == "timer":
            return _result(True, 0.9, "timer", "計時完成", source="heuristic")

        return _result(False, 0.25, "uncertain", "無法自動判斷，請手動確認", source="heuristic")

    except Exception as exc:
        return _result(False, 0.0, "error", f"分析失敗: {exc}", source="heuristic")


def _merge_results(gemini: Dict[str, Any], heuristic: Dict[str, Any]) -> Dict[str, Any]:
    """Prefer Gemini semantics but keep conservative auto-advance behavior."""
    confidence = float(gemini.get("confidence", 0.0))
    detected = bool(gemini.get("detected", False))

    if confidence < CONFIDENCE_THRESHOLD:
        detected = False

    # If Gemini is uncertain but heuristics are strong, surface that in message only.
    message = gemini.get("message", "")
    if confidence < CONFIDENCE_THRESHOLD and heuristic.get("confidence", 0) >= CONFIDENCE_THRESHOLD:
        message = f"{message}（本地 heuristics 有跡象，但仍需確認）"

    return {
        "detected": detected,
        "confidence": round(confidence, 2),
        "kind": gemini.get("kind", "gemini_vision"),
        "message": message,
        "needs_confirm": confidence < CONFIDENCE_THRESHOLD,
        "source": "gemini",
        "heuristic": {
            "detected": heuristic.get("detected"),
            "confidence": heuristic.get("confidence"),
            "kind": heuristic.get("kind"),
        },
    }


def _result(
    detected: bool,
    confidence: float,
    kind: str,
    message: str,
    source: str,
) -> Dict[str, Any]:
    return {
        "detected": detected,
        "confidence": round(confidence, 2),
        "kind": kind,
        "message": message,
        "needs_confirm": confidence < CONFIDENCE_THRESHOLD,
        "source": source,
    }


def vision_backend_status() -> Dict[str, Any]:
    return {
        "gemini_configured": bool(get_api_key()),
        "pillow_available": HAS_PIL,
        "mode": "gemini+heuristic" if get_api_key() else "heuristic",
    }
