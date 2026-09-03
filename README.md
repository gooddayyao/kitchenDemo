# AI Cooking Assistant Projection Demo

Spatial projection + semi-automatic camera cooking assistant for a fixed kitchen counter.

## Features (Phase 2–5)
- Structured recipes (`data/recipes/*.json`) with zones, timers, guidance types
- Step Engine: `pending` → `active` → `awaiting_confirm` → `done`
- Gemini recipe parsing via `/api/parse-recipe` (rule-based fallback when no API key)
- Spatial Canvas overlay with cut-line guides on counter zones
- Homography calibration (click four corners once, saved to localStorage + server)
- Per-step countdown timer (starts when step becomes active)
- Semi-automatic camera monitoring with confidence-based user confirmation
- Optional Gemini Vision analysis when `GEMINI_API_KEY` is configured

## Project Structure
- `main.py` — FastAPI backend
- `services/recipe_parser.py` — Gemini + rule-based recipe parsing
- `services/vision.py` — Semi-auto vision heuristics
- `data/recipes/` — Structured recipe JSON files
- `recipe_schema.json` — Web Recipe JSON schema（欄位說明見 [`RECIPE_FORMAT.md`](RECIPE_FORMAT.md)）
- `static/` — Frontend (step engine, calibration, overlay, vision, app)

## Run the demo
1. Create a Python 3.11+ virtual environment.
2. Install dependencies:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. (Optional) Set Gemini API key:
   ```powershell
   $env:GEMINI_API_KEY = "your-key"
   ```
4. Launch the app:
   ```powershell
   uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```
   Or run `start.bat`.
5. Open `http://127.0.0.1:8000` in Chrome or Edge.

## Run CV preview (webcam / phone)
```powershell
.\start-webcam.bat          # 本機 / USB 鏡頭（YOLO + 色彩小黃瓜）
.\start-phone.bat           # 手機 IP Webcam
.\start-gemini-track.bat    # Gemini 認物 + CSRT 追蹤（需 GEMINI_API_KEY）
```
```powershell
$env:GEMINI_API_KEY = "your-key"
python -m src.phone_test --webcam --gemini-track
```
按 `G` 可強制再問一次 Gemini；換步驟或追丟也會自動重認。

## Usage
1. Select a recipe (e.g. 香煎牛排) from the left panel.
2. Click **校正投影區域** and click four counter corners in projection mode.
3. Click **進入投影模式** — spatial hints appear on cutting board / stove zones.
4. Steps with `timer_seconds` start counting down when they become active.
5. Camera monitors pot/prep heuristics; low confidence shows a confirm prompt.
6. Click **確認完成** to advance when manual confirmation is needed.

## API Endpoints
- `GET /api/health` — Health check
- `GET /api/recipes` — List recipes
- `GET /api/recipes/{id}` — Get structured recipe
- `POST /api/parse-recipe` — Parse recipe text
- `GET/POST /api/calibration` — Calibration data
- `POST /api/vision/analyze` — Analyze camera frame

## Current Status
- **Completed:** Phase 1 UI scaffold; Phase 2 structured recipes + step engine; Phase 4 per-step timers; Phase 5 semi-auto vision (heuristic + optional Gemini)
- **In progress:** Phase 3 spatial projection/homography polish
- **Next:** Phase 6 voice Q&A (auxiliary); improve vision accuracy post-MVP

## Progress Sync
- Use GitHub as single source of truth.
- Update `PROJECT_PLAN.md` when phases change.
