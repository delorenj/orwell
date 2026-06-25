#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: $0 <in|out> <max_jitter_seconds> <tag> <screenshot_name>" >&2
  exit 2
fi

action="$1"
max_jitter_seconds="$2"
tag="$3"
screenshot_name="$4"

case "$action" in
  in|out) ;;
  *)
    echo "invalid action: $action" >&2
    exit 2
    ;;
esac

if ! [[ "$max_jitter_seconds" =~ ^[0-9]+$ ]]; then
  echo "max_jitter_seconds must be a non-negative integer" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$REPO/outputs/cron"
STAMP="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE="$LOG_DIR/${tag}_${STAMP}.log"
LOCK_FILE="/tmp/orwell-automation.lock"
SCREENSHOT="$REPO/outputs/${screenshot_name}"

mkdir -p "$LOG_DIR"
cd "$REPO"

exec >>"$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] starting ${tag}"
echo "repo=$REPO"
echo "log_file=$LOG_FILE"
echo "action=$action"
echo "screenshot=$SCREENSHOT"

if [ "${SKIP_IF_SCREENSHOT_TODAY:-0}" = "1" ] && [ -f "$SCREENSHOT" ] && [ "$(date -r "$SCREENSHOT" '+%Y-%m-%d')" = "$(date '+%Y-%m-%d')" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] skipping ${tag}; today's screenshot already exists"
  exit 0
fi

jitter_seconds="${JITTER_SECONDS:-}"
if [ -z "$jitter_seconds" ]; then
  jitter_seconds=$(( RANDOM % (max_jitter_seconds + 1) ))
fi

if ! [[ "$jitter_seconds" =~ ^[0-9]+$ ]]; then
  echo "jitter_seconds must be a non-negative integer" >&2
  exit 2
fi

if [ "$jitter_seconds" -gt "$max_jitter_seconds" ]; then
  echo "clamping jitter_seconds from $jitter_seconds to max $max_jitter_seconds"
  jitter_seconds="$max_jitter_seconds"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] jitter_seconds=$jitter_seconds"
if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] dry run enabled; not sleeping or executing browser automation"
  exit 0
fi

sleep "$jitter_seconds"
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] executing scripts/03_clock_action.py $action"

if /usr/bin/flock -n "$LOCK_FILE" .venv/bin/python scripts/03_clock_action.py "$action"; then
  :
else
  status=$?
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] ${tag} failed with exit=$status"
  exit "$status"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] ${tag} completed successfully"
