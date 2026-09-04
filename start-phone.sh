#!/usr/bin/env bash
# KITCHEN Phase 1 — 手機 IP Webcam
# 用法：
#   ./start-phone.sh
#   ./start-phone.sh 192.168.31.140
#   ./start-phone.sh 192.168.31.140:8080
#   ./start-phone.sh http://192.168.31.140:8080/video
#   ./start-phone.sh rtsp://192.168.31.140:8080/h264_ulaw.sdp

set -e
cd "$(dirname "$0")"

PYTHON=".venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=".venv/Scripts/python.exe"
fi
if [[ ! -f "$PYTHON" && ! -x "$PYTHON" ]]; then
  echo "[錯誤] 找不到 .venv，請先建立並 pip install -r requirements-cv.txt"
  exit 1
fi

ARG="${1:-10.179.115.150}"

if [[ -z "$ARG" ]]; then
  echo "[取消] 未輸入位址"
  exit 1
fi

if [[ "$ARG" =~ ^(https?|rtsps?):// ]]; then
  SOURCE="$ARG"
else
  HOST="$ARG"
  if [[ "$HOST" != *:* ]]; then
    HOST="${HOST}:8080"
  fi
  SOURCE="http://${HOST}/video"
fi

echo
echo "========================================"
echo " KITCHEN AR — 手機 IP Webcam"
echo " Source: $SOURCE"
echo " 畫面上方按鈕：重新開始 / 校正尺度 / 隱藏相機 / 下一步 / 離開"
echo "========================================"

exec "$PYTHON" -m src.phone_test --source "$SOURCE" --detect-every 2 --infer-width 480
