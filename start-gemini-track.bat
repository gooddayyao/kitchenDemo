@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM KITCHEN — Gemini 關鍵幀認物 + CSRT 追蹤（略過 YOLO）
REM 用法：
REM   start-gemini-track.bat
REM   start-gemini-track.bat 1
REM   start-gemini-track.bat http://192.168.x.x:8080/video

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [錯誤] 找不到 .venv
    pause
    exit /b 1
)

if "%GEMINI_API_KEY%"=="" (
    echo [錯誤] 請先設定 GEMINI_API_KEY
    echo   set GEMINI_API_KEY=your-key
    pause
    exit /b 1
)

set "ARG=%~1"
if "%ARG%"=="" set "ARG=0"

echo %ARG% | findstr /I /B "http:// https:// rtsp://" >nul
if %ERRORLEVEL%==0 (
    set "SRC_ARGS=--source %ARG%"
) else (
    set "SRC_ARGS=--webcam %ARG%"
)

echo ========================================
echo  KITCHEN AR — Gemini + CSRT track
echo  %SRC_ARGS%
echo  按 G 重新辨識；Q 離開
echo ========================================

.\.venv\Scripts\python.exe -m src.phone_test %SRC_ARGS% --gemini-track --detect-every 2 --infer-width 640
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" pause
exit /b %EXITCODE%
