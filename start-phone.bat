@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

REM KITCHEN Phase 1 — phone IP Webcam
REM Usage:
REM   start-phone.bat
REM   start-phone.bat 192.168.31.140
REM   start-phone.bat 192.168.31.140:8080
REM   start-phone.bat http://192.168.31.140:8080/video
REM   start-phone.bat rtsp://192.168.31.140:8080/h264_ulaw.sdp

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Run:
    echo   python -m venv .venv
    echo   .\.venv\Scripts\python.exe -m pip install -r requirements-cv.txt
    pause
    exit /b 1
)

set "ARG=%~1"
if "!ARG!"=="" (
    echo ========================================
    echo  KITCHEN AR — phone IP Webcam
    echo ========================================
    echo  1. Install IP Webcam on phone
    echo  2. PC joins phone hotspot / same Wi-Fi
    echo  3. App: Start server, note the IP
    echo.
    set /p ARG="Enter phone IP or full URL: "
)

REM trim spaces
for /f "tokens=* delims= " %%A in ("!ARG!") do set "ARG=%%A"

if "!ARG!"=="" (
    echo [cancel] no address entered
    pause
    exit /b 1
)

REM Build SOURCE with delayed expansion only (avoids empty IP bug)
set "SOURCE="
echo !ARG!| findstr /I /B /C:"http://" /C:"https://" /C:"rtsp://" /C:"rtsps://" >nul
if !ERRORLEVEL! EQU 0 (
    set "SOURCE=!ARG!"
) else (
    set "HOST=!ARG!"
    echo !HOST!| findstr ":" >nul
    if !ERRORLEVEL! NEQ 0 set "HOST=!HOST!:8080"
    set "SOURCE=http://!HOST!/video"
)

echo.
echo ========================================
echo  KITCHEN AR — phone IP Webcam
echo  Source: !SOURCE!
echo  Quit: Q / ESC / window X
echo ========================================
echo.

.\.venv\Scripts\python.exe -m src.phone_test --source "!SOURCE!" --detect-every 3 --infer-width 480
set "EXITCODE=!ERRORLEVEL!"

if not "!EXITCODE!"=="0" (
    echo.
    echo [FAIL] cannot open stream: !SOURCE!
    echo Check: phone Start server, IP correct, same hotspot/Wi-Fi.
    echo Try RTSP:
    echo   start-phone.bat rtsp://PHONE_IP:8080/h264_ulaw.sdp
    pause
)

exit /b !EXITCODE!
