# Project Plan: AI Cooking Assistant Projection Demo

## Current Work Goal
- Keep project progress synced across different machines.
- Use GitHub as the shared source of truth.
- Ensure the latest work is committed and pushed before switching devices.

## Project Phases

### Phase 1 - Project Structure and UI Mockup
- Status: Completed
- Deliverables:
  - Static frontend mockup (`index.html`, `style.css`, `app.js`)
  - Basic FastAPI backend (`main.py`)
  - README and project scaffold

### Phase 2 - Gemini Recipe Parsing
- Status: In progress
- Goals:
  - Integrate Gemini API for recipe parsing
  - Implement `/api/parse-recipe` endpoint
  - Connect frontend form to backend parse flow

### Phase 3 - Projection Mode
- Status: Planned
- Goals:
  - Add full-screen projection view
  - Optimize layout for second-screen display
  - Add step progress and timer UI

### Phase 4 - Voice Interaction
- Status: Planned
- Goals:
  - Add microphone input for questions
  - Add browser TTS for Gemini responses
  - Connect voice flow with recipe and step context

## Sync workflow
1. On each machine, run `git pull origin main` before starting work.
2. Make changes locally and test.
3. Commit with a clear message.
4. Push to `origin main`.
5. On another machine, run `git pull origin main` before continuing.

## Notes
- Do not rely on local-only state; keep progress in Git commits and the project plan.
- If a machine is offline, save work locally and push when reconnected.
