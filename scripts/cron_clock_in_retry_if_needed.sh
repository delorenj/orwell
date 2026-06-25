#!/usr/bin/env bash
set -euo pipefail

REPO="/home/delorenj/code/clockin"
LOG_DIR="$REPO/outputs/cron"
STAMP="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE="$LOG_DIR/clock_in_retry_${STAMP}.log"
SCREENSHOT="$REPO/outputs/clock_in.png"
LOCK_FILE="/tmp/clockin-automation.lock"
TODAY="$(date '+%Y-%m-%d')"

mkdir -p "$LOG_DIR"
cd "$REPO"

exec >>"$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] retry watchdog starting"

if [ -f "$SCREENSHOT" ] && [ "$(date -r "$SCREENSHOT" '+%Y-%m-%d')" = "$TODAY" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] skipping retry; today's clock_in.png already exists"
  exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] no successful screenshot detected for today; retrying clock-in"
if ! /usr/bin/flock -n "$LOCK_FILE" .venv/bin/python scripts/03_clock_action.py in; then
  status=$?
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] retry failed with exit=$status"
  exit "$status"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] retry completed successfully"
