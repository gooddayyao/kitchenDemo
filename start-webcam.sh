#!/usr/bin/env bash
# KITCHEN Phase 1 — 本機鏡頭 / USB Webcam
# 用法：
#   ./start-webcam.sh
#   ./start-webcam.sh 1
#   ./start-webcam.sh --list

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

if [[ "${1:-}" == "--list" ]]; then
  echo "正在掃描可用鏡頭…"
  "$PYTHON" -m src.phone_test --list-cameras
  exit 0
fi

CAM_INDEX="${1:-0}"
echo "========================================"
echo " KITCHEN AR — 本機 / USB Webcam"
echo " Camera index: $CAM_INDEX"
echo " 關閉：Q / ESC / 視窗 X"
echo "========================================"
exec "$PYTHON" -m src.phone_test --webcam "$CAM_INDEX" --detect-every 2 --infer-width 640
