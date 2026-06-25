#!/usr/bin/env bash
set -euo pipefail

REPO="/home/delorenj/code/clockin"
LOG_DIR="$REPO/outputs/cron"
STAMP="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE="$LOG_DIR/clock_in_once_${STAMP}.log"
LOCK_FILE="/tmp/clockin-automation.lock"

mkdir -p "$LOG_DIR"
cd "$REPO"

exec >>"$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] starting clock-in automation"
echo "repo=$REPO"
echo "log_file=$LOG_FILE"

if ! /usr/bin/flock -n "$LOCK_FILE" .venv/bin/python scripts/03_clock_action.py in; then
  status=$?
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] clock-in automation failed with exit=$status"
  exit "$status"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] clock-in automation completed successfully"
