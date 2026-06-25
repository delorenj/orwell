#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <in|out> <tag> <screenshot_name>" >&2
  exit 2
fi

action="$1"
tag="$2"
screenshot_name="$3"

case "$action" in
  in|out) ;;
  *)
    echo "invalid action: $action" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$REPO/outputs/cron"
STAMP="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE="$LOG_DIR/${tag}_${STAMP}.log"
LOCK_FILE="/tmp/orwell-automation.lock"
SCREENSHOT="$REPO/outputs/${screenshot_name}"
TODAY="$(date '+%Y-%m-%d')"

mkdir -p "$LOG_DIR"
cd "$REPO"

exec >>"$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] starting ${tag}"
echo "repo=$REPO"
echo "log_file=$LOG_FILE"
echo "action=$action"

if [ -f "$SCREENSHOT" ] && [ "$(date -r "$SCREENSHOT" '+%Y-%m-%d')" = "$TODAY" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] skipping ${tag}; today's screenshot already exists"
  exit 0
fi

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] dry run enabled; not executing browser automation"
  exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] no screenshot detected for today; executing retry"
if /usr/bin/flock -n "$LOCK_FILE" .venv/bin/python scripts/03_clock_action.py "$action"; then
  :
else
  status=$?
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] ${tag} failed with exit=$status"
  exit "$status"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] ${tag} completed successfully"
