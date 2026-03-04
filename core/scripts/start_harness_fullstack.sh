#!/usr/bin/env bash
# LAYER OS Fullstack Harness (local/operator entrypoint)
# Starts the core collaboration loop + optional scout/gardener/monitor.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

LOGS_DIR="$PROJECT_ROOT/.infra/logs"
mkdir -p "$LOGS_DIR"

WITH_SCOUT=1
WITH_GARDENER=0
WITH_MONITOR=0
WITH_GATEWAY=1
SCOUT_INTERVAL=6
GATEWAY_PORT=8082
SKIP_BOOTSTRAP=0
SKIP_PLAN_COUNCIL_CHECK=0

usage() {
  cat <<'EOF'
Usage:
  bash core/scripts/start_harness_fullstack.sh [options]

Options:
  --no-scout            Disable scout agent
  --with-gardener       Enable gardener schedule mode
  --with-monitor        Enable monitor dashboard (refresh mode)
  --no-gateway          Disable unified backend gateway
  --gateway-port N      Gateway bind port (default: 8082)
  --scout-interval N    Scout polling interval in hours (default: 6)
  --skip-bootstrap      Skip session bootstrap gate
  --skip-plan-council-check  Skip plan council self-check
  -h, --help            Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-scout)
      WITH_SCOUT=0
      shift
      ;;
    --with-gardener)
      WITH_GARDENER=1
      shift
      ;;
    --with-monitor)
      WITH_MONITOR=1
      shift
      ;;
    --no-gateway)
      WITH_GATEWAY=0
      shift
      ;;
    --gateway-port)
      GATEWAY_PORT="${2:-8082}"
      shift 2
      ;;
    --scout-interval)
      SCOUT_INTERVAL="${2:-6}"
      shift 2
      ;;
    --skip-bootstrap)
      SKIP_BOOTSTRAP=1
      shift
      ;;
    --skip-plan-council-check)
      SKIP_PLAN_COUNCIL_CHECK=1
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

if [[ "$SKIP_BOOTSTRAP" != "1" ]]; then
  bash core/scripts/session_bootstrap.sh
fi

# Load .env for local runs (systemd environments already inject this).
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  if "$PYTHON_BIN" -c "import dotenv" >/dev/null 2>&1; then
    while IFS= read -r kv; do
      [[ -z "$kv" ]] && continue
      export "$kv"
    done < <("$PYTHON_BIN" - <<'PY'
from dotenv import dotenv_values

for key, value in dotenv_values(".env").items():
    if not key or value is None:
        continue
    print(f"{key}={value}")
PY
)
  else
    echo "WARN: python-dotenv not importable in $PYTHON_BIN. skipping .env load."
  fi
fi

if [[ -z "${GOOGLE_API_KEY:-}" && -z "${GEMINI_API_KEY:-}" ]]; then
  echo "WARN: GOOGLE_API_KEY/GEMINI_API_KEY not found."
  echo "      SA/AD/CE/Gardener may fail immediately."
fi

if [[ "$WITH_GATEWAY" == "1" ]]; then
  if [[ -z "${FASTAPI_ADMIN_PASSWORD_HASH:-}" ]]; then
    echo "WARN: FASTAPI_ADMIN_PASSWORD_HASH not set. backend gateway disabled."
    WITH_GATEWAY=0
  elif ! "$PYTHON_BIN" -c "import uvicorn" >/dev/null 2>&1; then
    echo "WARN: uvicorn not importable in $PYTHON_BIN. backend gateway disabled."
    WITH_GATEWAY=0
  fi
fi

if [[ "$SKIP_PLAN_COUNCIL_CHECK" != "1" ]]; then
  "$PYTHON_BIN" core/system/plan_council.py --self-check --require-both
fi

declare -a PIDS=()

start_proc() {
  local log_name="$1"
  shift
  "$PYTHON_BIN" -u "$@" >> "$LOGS_DIR/${log_name}.log" 2>&1 &
  local pid=$!
  PIDS+=("$pid")
  echo "started: ${log_name} (pid=${pid})"
}

cleanup() {
  echo ""
  echo "stopping harness..."
  if [[ ${#PIDS[@]} -gt 0 ]]; then
    kill "${PIDS[@]}" 2>/dev/null || true
    wait "${PIDS[@]}" 2>/dev/null || true
  fi
  echo "harness stopped"
  exit 0
}
trap cleanup SIGINT SIGTERM

echo "=== LAYER OS Fullstack Harness ==="
echo "python: $PYTHON_BIN"
echo "logs:   $LOGS_DIR"
echo "scout:  $WITH_SCOUT (interval=${SCOUT_INTERVAL}h)"
echo "gardener: $WITH_GARDENER"
echo "monitor:  $WITH_MONITOR"
echo "gateway:  $WITH_GATEWAY (port=${GATEWAY_PORT})"
echo "=================================="

# Core collaboration loop
start_proc "filesystem_guard" core/system/filesystem_guard.py
start_proc "sa_agent" core/agents/sa_agent.py
start_proc "ad_agent" core/agents/ad_agent.py
start_proc "ce_agent" core/agents/ce_agent.py
start_proc "cd_agent" core/agents/cd_agent.py
start_proc "orchestrator" core/system/pipeline_orchestrator.py

if [[ "$WITH_GATEWAY" == "1" ]]; then
  start_proc "backend_gateway" -m uvicorn core.backend.main:app --host 127.0.0.1 --port "$GATEWAY_PORT"
fi

# Optional modules
if [[ "$WITH_SCOUT" == "1" ]]; then
  start_proc "scout_agent" core/agents/scout_agent.py --forever --interval "$SCOUT_INTERVAL"
fi

if [[ "$WITH_GARDENER" == "1" ]]; then
  start_proc "gardener" core/agents/gardener.py --schedule --hour 3
fi

if [[ "$WITH_MONITOR" == "1" ]]; then
  start_proc "monitor_dashboard" core/system/monitor_dashboard.py --refresh 15
fi

echo ""
echo "fullstack harness running (Ctrl+C to stop)"
wait
