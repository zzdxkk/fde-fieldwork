#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../app"
python3 -m pip install --no-index --find-links=../deploy/wheels -r ../deploy/requirements.txt 2>/dev/null || true
python3 main.py
echo "[OK] 报告输出在 ../out/"
