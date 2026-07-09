@echo off
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q
uvicorn main:app --reload --host 127.0.0.1 --port 8100
