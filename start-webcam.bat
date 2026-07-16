@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM KITCHEN Phase 1 — 本機鏡頭 / USB Webcam
REM 用法：
REM   start-webcam.bat          → 預設鏡頭 (index 0)
REM   start-webcam.bat 1        → 第二顆鏡頭
REM   start-webcam.bat --list   → 列出可用鏡頭

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [錯誤] 找不到 .venv，請先：
    echo   python -m venv .venv
    echo   .\.venv\Scripts\Activate.ps1
    echo   pip install -r requirements-cv.txt
    pause
    exit /b 1
)

if /I "%~1"=="--list" (
    echo 正在掃描可用鏡頭…
    .\.venv\Scripts\python.exe -m src.phone_test --list-cameras
    pause
    exit /b 0
)

set "CAM_INDEX=0"
if not "%~1"=="" set "CAM_INDEX=%~1"

echo ========================================
echo  KITCHEN AR — 本機 / USB Webcam
echo  Camera index: %CAM_INDEX%
echo  關閉：Q / ESC / 視窗 X
echo ========================================
echo.

.\.venv\Scripts\python.exe -m src.phone_test --webcam %CAM_INDEX% --detect-every 2 --infer-width 640
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [失敗] 無法開啟鏡頭 index %CAM_INDEX%
    echo   start-webcam.bat --list
    echo   start-webcam.bat 1
    pause
)

exit /b %EXITCODE%
