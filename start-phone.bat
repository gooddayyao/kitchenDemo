@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM KITCHEN Phase 1 — 手機 IP Webcam
REM 用法：
REM   start-phone.bat
REM   start-phone.bat 192.168.31.140
REM   start-phone.bat 192.168.31.140:8080
REM   start-phone.bat http://192.168.31.140:8080/video
REM   start-phone.bat rtsp://192.168.31.140:8080/h264_ulaw.sdp

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [錯誤] 找不到 .venv，請先：
    echo   python -m venv .venv
    echo   .\.venv\Scripts\Activate.ps1
    echo   pip install -r requirements-cv.txt
    pause
    exit /b 1
)

set "ARG=%~1"
if "%ARG%"=="" (
    echo ========================================
    echo  KITCHEN AR — 手機 IP Webcam
    echo ========================================
    echo  1. 手機安裝 IP Webcam，與 PC 同一 Wi-Fi
    echo  2. App 按 Start server，記下 IP
    echo.
    set /p ARG="請輸入手機 IP 或完整 URL: "
)

if "%ARG%"=="" (
    echo [取消] 未輸入位址
    pause
    exit /b 1
)

REM 若已是完整 URL，直接使用；否則組出 HTTP /video
echo %ARG% | findstr /I /B "http:// https:// rtsp:// rtsps://" >nul
if %ERRORLEVEL%==0 (
    set "SOURCE=%ARG%"
) else (
    set "HOST=%ARG%"
    echo %HOST% | findstr ":" >nul
    if errorlevel 1 set "HOST=%HOST%:8080"
    set "SOURCE=http://!HOST!/video"
)

echo.
echo ========================================
echo  KITCHEN AR — 手機 IP Webcam
echo  Source: %SOURCE%
echo  關閉：Q / ESC / 視窗 X
echo ========================================
echo.

REM 手機串流延遲較高，預設較省資源
.\.venv\Scripts\python.exe -m src.phone_test --source "%SOURCE%" --detect-every 3 --infer-width 480
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [失敗] 無法開啟串流：%SOURCE%
    echo 請確認手機已 Start server，且 IP / 防火牆正確。
    echo 也可試 RTSP：
    echo   start-phone.bat rtsp://手機IP:8080/h264_ulaw.sdp
    pause
)

exit /b %EXITCODE%
