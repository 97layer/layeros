#!/usr/bin/env bash
# council-room-watch.sh — UserPromptSubmit hook
# Sync council_room proposals into shared queue and print compact status.

set -euo pipefail

PROJECT_ROOT="/Users/97layer/97layerOS"
SCRIPT="$PROJECT_ROOT/core/scripts/council_issue_loop.py"
LOG_DIR="$PROJECT_ROOT/.infra/logs"
LOG_FILE="$LOG_DIR/council-room-watch.log"

# Consume hook input JSON so the hook chain remains stable.
cat >/dev/null || true

if [[ ! -f "$SCRIPT" ]]; then
  exit 0
fi

mkdir -p "$LOG_DIR"

if ! output="$(python3 "$SCRIPT" watch --max-items 3 --quiet-empty 2>&1)"; then
  while IFS= read -r line; do
    printf '[%s] ERROR %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$line" >>"$LOG_FILE"
  done <<<"$output"
  exit 0
fi

if [[ -n "$output" ]]; then
  while IFS= read -r line; do
    printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$line" >>"$LOG_FILE"
  done <<<"$output"
  printf '%s\n' "$output"
fi
exit 0
