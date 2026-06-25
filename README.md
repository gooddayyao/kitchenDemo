# AI Cooking Assistant Projection Demo

## Phase 1 - Project Structure and UI Mockup

This prototype demonstrates the initial structure for a cooking assistant projection demo.

### What is included
- `main.py`: FastAPI backend serving the demo UI
- `static/index.html`: Browser UI mockup
- `static/style.css`: Layout and projection-style design
- `static/app.js`: UI state, step navigation, and mock data
- `requirements.txt`: Python dependencies

### Run the demo
1. Create a Python 3.11+ virtual environment.
2. Install dependencies:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Launch the app:
   ```powershell
   uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```
4. Open `http://127.0.0.1:8000` in Chrome or Edge.

### Notes
- This phase focuses on a projection-ready UI mockup and basic backend staging.
- Gemini API and voice integration are planned for later phases.
