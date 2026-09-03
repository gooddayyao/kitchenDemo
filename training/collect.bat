@echo off
chcp 65001 >nul
setlocal

REM 依類別蒐集網圖（預設 Wikimedia Commons + YOLO-World 自動標框）
REM 用法：
REM   collect.bat cucumber
REM   collect.bat 小黃瓜 番茄 --max 40
REM   collect.bat cucumber --source web

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [錯誤] 找不到 .venv，請先：
    echo   python -m venv .venv
    echo   .\.venv\Scripts\Activate.ps1
    echo   pip install -r requirements-cv.txt
    pause
    exit /b 1
)

if "%~1"=="" (
    echo 請指定類別，例如：
    echo   collect.bat cucumber
    echo   collect.bat 小黃瓜 番茄 --max 40
    pause
    exit /b 1
)

.\.venv\Scripts\python.exe training\collect.py %*
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [失敗] 蒐集未完成，請看上方訊息與 training\README.md
    pause
)

exit /b %EXITCODE%
