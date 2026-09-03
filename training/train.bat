@echo off
chcp 65001 >nul
setlocal

REM Kitchen YOLOv8 訓練
REM 用法：
REM   train.bat
REM   train.bat --epochs 80 --imgsz 640

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [錯誤] 找不到 .venv，請先：
    echo   python -m venv .venv
    echo   .\.venv\Scripts\Activate.ps1
    echo   pip install -r requirements-cv.txt
    pause
    exit /b 1
)

echo ========================================
echo  KITCHEN — YOLOv8 訓練
echo  資料：training\dataset\
echo  設定：training\kitchen.yaml
echo ========================================
echo.

.\.venv\Scripts\python.exe training\train.py %*
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [失敗] 訓練未完成，請看上方訊息與 training\README.md
    pause
)

exit /b %EXITCODE%
