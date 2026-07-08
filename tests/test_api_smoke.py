"""Lightweight API smoke tests for the cooking assistant demo."""

from __future__ import annotations

import base64
import io
import json
import sys
import urllib.error
import urllib.request
from typing import Optional, Tuple

BASE = "http://127.0.0.1:8000"


def request(method: str, path: str, payload: Optional[dict] = None) -> Tuple[int, dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"detail": body}


def tiny_png_b64() -> str:
    try:
        from PIL import Image
    except ImportError:
        return ""
    img = Image.new("L", (64, 64), color=180)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def main() -> int:
    failures = []

    status, health = request("GET", "/api/health")
    if status != 200 or health.get("status") != "ok":
        failures.append(f"health failed: {status} {health}")
    elif "steak" not in health.get("recipes", []):
        failures.append(f"health missing steak recipe: {health}")
    elif health.get("vision_mode") not in ("heuristic", "gemini+heuristic"):
        failures.append(f"health missing vision_mode: {health}")

    status, recipes = request("GET", "/api/recipes")
    if status != 200 or len(recipes.get("recipes", [])) < 2:
        failures.append(f"recipes list failed: {status} {recipes}")

    status, steak = request("GET", "/api/recipes/steak")
    if status != 200 or steak.get("title") != "香煎牛排":
        failures.append(f"steak recipe failed: {status} {steak}")
    else:
        step2 = next((s for s in steak["steps"] if s["step"] == 2), None)
        if not step2 or step2.get("timer_seconds") != 180:
            failures.append(f"steak step2 timer wrong: {step2}")

    status, parsed = request("POST", "/api/parse-recipe", {"text": "### 食譜名稱：測試\n#### 材料：\n- [ ] 蛋 1 顆\n#### 步驟：\n- [ ] **步驟 1：** 打蛋 2 分鐘"})
    if status != 200 or not parsed.get("steps"):
        failures.append(f"parse-recipe failed: {status} {parsed}")

    status, calib = request("POST", "/api/calibration", {
        "corners": [
            {"x": 0, "y": 0},
            {"x": 100, "y": 0},
            {"x": 100, "y": 100},
            {"x": 0, "y": 100},
        ]
    })
    if status != 200 or calib.get("status") != "saved":
        failures.append(f"calibration save failed: {status} {calib}")

    img = tiny_png_b64()
    if img:
        status, vision = request("POST", "/api/vision/analyze", {
            "image": img,
            "step_context": {"completion": "vision_heuristic", "zone": "stove", "motion_score": 0.05},
        })
        if status != 200 or "confidence" not in vision:
            failures.append(f"vision analyze failed: {status} {vision}")
        elif vision.get("source") not in ("heuristic", "gemini"):
            failures.append(f"vision source missing: {vision}")

    try:
        with urllib.request.urlopen(BASE + "/", timeout=10) as resp:
            html = resp.read().decode("utf-8")
            if resp.status != 200 or "AI Cooking Assistant" not in html:
                failures.append(f"index page failed: {resp.status}")
    except Exception as exc:
        failures.append(f"index page failed: {exc}")

    if failures:
        print("E2E FAILED:")
        for item in failures:
            print(" -", item)
        return 1

    print("E2E PASSED: health, recipes, steak, parse-recipe, calibration, vision, index")
    return 0


if __name__ == "__main__":
    sys.exit(main())
