#!/usr/bin/env bash
# Run resilience smoke and persist a compact operational trail.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="/tmp/woohwahae-resilience-smoke.log"
CMD='python3 core/scripts/pipeline_resilience_smoke.py'

cd "$PROJECT_ROOT"

timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "[$timestamp] START resilience_smoke" >>"$LOG_FILE"

if python3 core/system/evidence_guard.py --check >/dev/null 2>&1; then
  if python3 core/scripts/pipeline_resilience_smoke.py >>"$LOG_FILE" 2>&1; then
    python3 core/system/evidence_guard.py --append \
      --claim "Scheduled resilience smoke passed" \
      --evidence-type command \
      --source "$CMD" \
      --detail "scheduled=true status=pass timestamp_utc=$timestamp" >/dev/null 2>&1 || true
    echo "[$timestamp] PASS resilience_smoke" >>"$LOG_FILE"
    exit 0
  fi
fi

python3 core/system/evidence_guard.py --append \
  --claim "Scheduled resilience smoke failed" \
  --evidence-type command \
  --source "$CMD" \
  --detail "scheduled=true status=fail timestamp_utc=$timestamp" >/dev/null 2>&1 || true
echo "[$timestamp] FAIL resilience_smoke" >>"$LOG_FILE"
exit 1

