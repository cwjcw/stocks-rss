#!/usr/bin/env bash
set -euo pipefail

# 统一时区
export TZ=Asia/Shanghai

ROOT="/home/cwj/code/stocks-rss"
PY="$ROOT/venv/bin/python"
LOGF="/home/cwj/code/stocks-rss/logs/run.log"
LOCK="/home/cwj/.cache/stocks-rss.lock"

mkdir -p "$(dirname "$LOGF")"

# 用 flock 防止任务重叠
/usr/bin/flock -n "$LOCK" bash -c '
  cd "'"$ROOT"'"
  echo "[$(date +%F\ %T)] START build_all.py" >> "'"$LOGF"'"
  "'"$PY"'" "'"$ROOT"'/src/build_all.py" >> "'"$LOGF"'" 2>&1
  echo "[$(date +%F\ %T)] DONE" >> "'"$LOGF"'"
'
