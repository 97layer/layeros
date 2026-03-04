#!/usr/bin/env bash
# LAYER OS Harness Status Helper
# Quick operator view for unified gateway + orchestrator health.

set -euo pipefail

PORT=8082
HOST="127.0.0.1"
SHOW_RAW=0

usage() {
  cat <<'EOF'
Usage:
  bash core/scripts/harness_status.sh [options]

Options:
  --port N         Gateway port (default: 8082)
  --host HOST      Gateway host (default: 127.0.0.1)
  --raw            Print raw JSON payloads
  -h, --help       Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      PORT="${2:-8082}"
      shift 2
      ;;
    --host)
      HOST="${2:-127.0.0.1}"
      shift 2
      ;;
    --raw)
      SHOW_RAW=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

BASE_URL="http://${HOST}:${PORT}"
HEALTH_URL="${BASE_URL}/healthz"
STATUS_URL="${BASE_URL}/harness/status"

if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl is required."
  exit 1
fi

HEALTH_JSON=""
STATUS_JSON=""

if ! HEALTH_JSON="$(curl -fsS --max-time 2 "$HEALTH_URL")"; then
  echo "gateway: down (${HEALTH_URL} unreachable)"
  exit 2
fi

if ! STATUS_JSON="$(curl -fsS --max-time 2 "$STATUS_URL")"; then
  echo "gateway: up, harness/status unavailable"
  if [[ "$SHOW_RAW" == "1" ]]; then
    echo "healthz: $HEALTH_JSON"
  fi
  exit 3
fi

if [[ "$SHOW_RAW" == "1" ]]; then
  echo "healthz: $HEALTH_JSON"
  echo "harness/status: $STATUS_JSON"
  exit 0
fi

python3 - <<'PY' "$HEALTH_JSON" "$STATUS_JSON"
import json
import sys

health = json.loads(sys.argv[1])
status = json.loads(sys.argv[2])

services = health.get("services", {})
queue = status.get("queue", {}).get("counts", {})
orchestrator = health.get("orchestrator", {}).get("running")

print(f"gateway_status: {health.get('status', 'unknown')}")
print(f"orchestrator_running: {orchestrator}")
print(f"plan_council_status: {health.get('plan_council', {}).get('status', 'unknown')}")
print(f"queue: pending={queue.get('pending', 0)} processing={queue.get('processing', 0)} completed={queue.get('completed', 0)}")
print("services:")
for name, info in services.items():
    mounted = info.get("mounted")
    err = info.get("error") or "-"
    print(f"  - {name}: mounted={mounted} error={err}")
PY

