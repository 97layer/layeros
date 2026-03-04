#!/usr/bin/env bash
# Minimal production gate: visual validator + browser smoke + payment regressions.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PORT="9799"
BASE_URL=""
SESSION="og$(date +%H%M%S)"
WIDTHS="390,768,1440"
HEIGHT="900"
START_LOCAL_SERVER=1
HEADED=0
SKIP_VISUAL=0
SKIP_SMOKE=0
SKIP_PAYMENT=0
SERVER_PID=""

usage() {
  cat <<'EOF'
Usage:
  bash core/scripts/ops_gate.sh [options]

Options:
  --base-url URL      Base URL for smoke check (default: http://127.0.0.1:9799)
  --port N            Local server port when auto-serving (default: 9799)
  --session NAME      Playwright session name (default: ogHHMMSS)
  --widths CSV        Viewport widths (default: 390,768,1440)
  --height N          Viewport height (default: 900)
  --headed            Run Playwright in headed mode
  --no-serve          Do not auto-start local static server
  --skip-visual       Skip python3 core/system/visual_validator.py
  --skip-smoke        Skip live UI smoke monitor
  --skip-payment      Skip payment regression tests
  -h, --help          Show help

Examples:
  bash core/scripts/ops_gate.sh
  bash core/scripts/ops_gate.sh --base-url http://localhost:9700 --no-serve
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-9799}"
      shift 2
      ;;
    --session)
      SESSION="${2:-$SESSION}"
      shift 2
      ;;
    --widths)
      WIDTHS="${2:-$WIDTHS}"
      shift 2
      ;;
    --height)
      HEIGHT="${2:-$HEIGHT}"
      shift 2
      ;;
    --headed)
      HEADED=1
      shift
      ;;
    --no-serve)
      START_LOCAL_SERVER=0
      shift
      ;;
    --skip-visual)
      SKIP_VISUAL=1
      shift
      ;;
    --skip-smoke)
      SKIP_SMOKE=1
      shift
      ;;
    --skip-payment)
      SKIP_PAYMENT=1
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

if [[ -z "$BASE_URL" ]]; then
  BASE_URL="http://127.0.0.1:${PORT}"
fi

cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ "$START_LOCAL_SERVER" -eq 1 ]]; then
  echo "[ops-gate] start local static server on ${PORT}"
  python3 -m http.server "$PORT" --directory "$PROJECT_ROOT/website" --bind 127.0.0.1 >/tmp/woohwahae-ops-gate-http.log 2>&1 &
  SERVER_PID="$!"
  for _ in $(seq 1 20); do
    if curl -fsS --max-time 1 "${BASE_URL}/" >/dev/null 2>&1; then
      break
    fi
    sleep 0.2
  done
  if ! curl -fsS --max-time 1 "${BASE_URL}/" >/dev/null 2>&1; then
    echo "[ops-gate] local server is not reachable: ${BASE_URL}" >&2
    exit 2
  fi
fi

cd "$PROJECT_ROOT"

if [[ "$SKIP_VISUAL" -eq 0 ]]; then
  echo "[ops-gate] visual validator"
  python3 core/system/visual_validator.py
fi

if [[ "$SKIP_SMOKE" -eq 0 ]]; then
  if ! command -v npx >/dev/null 2>&1; then
    echo "[ops-gate] npx is required for Playwright smoke check" >&2
    exit 3
  fi
  echo "[ops-gate] browser smoke"
  URLS="${BASE_URL}/,${BASE_URL}/about/,${BASE_URL}/archive/,${BASE_URL}/practice/,${BASE_URL}/product/"
  MONITOR_ARGS=(
    python3 core/scripts/live_ui_monitor.py
    --once
    --session "$SESSION"
    --urls "$URLS"
    --widths "$WIDTHS"
    --height "$HEIGHT"
    --always-print
  )
  if [[ "$HEADED" -eq 1 ]]; then
    MONITOR_ARGS+=(--headed)
  fi
  "${MONITOR_ARGS[@]}"
fi

if [[ "$SKIP_PAYMENT" -eq 0 ]]; then
  echo "[ops-gate] payment regressions"
  pytest -q core/tests/test_ecommerce_payments_router.py core/tests/test_ecommerce_payment_service.py
fi

echo "[ops-gate] PASS"
