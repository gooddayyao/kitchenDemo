# Project Plan: AI Cooking Assistant Projection Demo

## Product Vision
A spatial projection + semi-automatic camera cooking assistant for a fixed kitchen counter setup. The projector displays guidance next to ingredients and cookware; the camera monitors prep and cooking progress with user confirmation when confidence is low.

## Current Work Goal
- Implement structured recipes, step engine, spatial projection overlays, per-step timers, and semi-auto vision.
- Keep project progress synced across machines via GitHub.

## Project Phases

### Phase 1 — Project Structure and UI Mockup
- **Status:** Completed
- **Deliverables:**
  - FastAPI backend (`main.py`)
  - Static frontend (`static/index.html`, `style.css`, `app.js`)
  - Basic fullscreen projection mode
  - README and project scaffold

### Phase 2 — Structured Recipes and Step Engine
- **Status:** In progress
- **Goals:**
  - Define recipe schema (`recipe_schema.json`, `data/recipes/*.json`)
  - Implement `/api/parse-recipe` with Gemini (fallback to local structured recipes)
  - Frontend Step Engine: `pending` → `active` → `awaiting_confirm` → `done`
  - Load recipes from API instead of hardcoded mock data

### Phase 3 — Spatial Projection and Calibration
- **Status:** In progress
- **Goals:**
  - Full-screen Canvas/SVG overlay for spatial hints
  - Projector-camera homography calibration (fixed install, save once)
  - Work zones: cutting board, stove, prep area
  - Cut-line guidance templates projected on counter zones

### Phase 4 — Per-Step Timer
- **Status:** In progress
- **Goals:**
  - Start countdown when step enters `active` and `timer_seconds > 0`
  - Display step timer near relevant zone (not total recipe remaining time)
  - On timer end → `awaiting_confirm` or auto-advance per `completion` rule

### Phase 5 — Semi-Automatic Camera Monitoring
- **Status:** Completed (heuristic MVP); Gemini Vision extension added
- **Goals:**
  - Camera preview (corner, non-intrusive)
  - Timer completion, marker/checkbox detection, simple pot motion heuristics
  - Return `confidence`; low confidence → projection prompt for user confirm
  - Do not auto-advance when uncertain
- **Phase 5 extension — Gemini Vision:**
  - When `GEMINI_API_KEY` is set, `/api/vision/analyze` uses Gemini image understanding via REST API
  - Falls back to local heuristics when API unavailable or confidence is low

### Phase 6 — Voice Interaction (Auxiliary)
- **Status:** Planned
- **Goals:**
  - Microphone Q&A + browser TTS for step-context questions
  - Does not replace step engine or spatial visual guidance

## MVP Demo Acceptance
1. Load steak recipe from structured data
2. Project cut-line guides on cutting board zone
3. Start 3-minute countdown when searing step becomes active
4. Advance on timer end or user confirmation
5. Camera low-confidence shows confirm prompt, no false auto-advance
6. With `GEMINI_API_KEY`, vision API uses Gemini image understanding (REST) with heuristic fallback

## Sync Workflow
1. On each machine, run `git pull origin main` before starting work.
2. Make changes locally and test.
3. Commit with a clear message.
4. Push to `origin main`.
5. On another machine, run `git pull origin main` before continuing.

## Notes
- Hardware mounting is out of scope; software assumes fixed projector + camera with one-time calibration.
- Semi-automatic vision is the MVP target; full ingredient recognition is post-MVP.
- Do not rely on local-only state for recipe progress; persist calibration in localStorage, recipes via API.
