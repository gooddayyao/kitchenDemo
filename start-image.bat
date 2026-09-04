@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM KITCHEN Phase 1 — cucumber image demo
REM Usage:
REM   start-image.bat path\to\cucumber.jpg

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Run:
    echo   python -m venv .venv
    echo   .\.venv\Scripts\python.exe -m pip install -r requirements-cv.txt
    pause
    exit /b 1
)

if "%~1"=="" (
    echo Usage: start-image.bat path\to\cucumber.jpg
    echo Example: start-image.bat data\demo\cucumber.jpg
    pause
    exit /b 1
)

if not exist "%~1" (
    echo [ERROR] Image not found: %~1
    pause
    exit /b 1
)

echo ========================================
echo  KITCHEN AR — Cucumber image demo
echo  Image: %~1
echo  畫面上方按鈕：重新開始 / 校正尺度 / 隱藏相機 / 下一步 / 離開
echo ========================================
echo.

.\.venv\Scripts\python.exe -m src.phone_test --image "%~1"
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [FAILED] Could not open image
    pause
)

exit /b %EXITCODE%
