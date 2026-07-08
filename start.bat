@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM 進入專案目錄
cd /d "%~dp0"

REM 激活虛擬環境
call .venv\Scripts\activate.bat

REM 啟動應用程式
echo 正在啟動應用程式...
start http://localhost:8000
timeout /t 2

REM 運行 FastAPI 伺服器
uvicorn main:app --reload --host 0.0.0.0 --port 8000

pause
