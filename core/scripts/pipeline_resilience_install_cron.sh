#!/usr/bin/env bash
# Install/update cron entry for pipeline resilience smoke runner.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

SCHEDULE="*/20 * * * *"
PRINT_ONLY=0

usage() {
  cat <<'EOF'
Usage:
  bash core/scripts/pipeline_resilience_install_cron.sh [options]

Options:
  --schedule "CRON"   Cron schedule (default: */20 * * * *)
  --print-only        Print target cron line without installing
  -h, --help          Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --schedule)
      SCHEDULE="${2:-$SCHEDULE}"
      shift 2
      ;;
    --print-only)
      PRINT_ONLY=1
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

RUNNER_CMD="/bin/bash -lc 'cd ${PROJECT_ROOT} && ./core/scripts/pipeline_resilience_runner.sh'"
CRON_TAG="# WOOHWAHAE_PIPELINE_RESILIENCE"
CRON_LINE="${SCHEDULE} ${RUNNER_CMD} ${CRON_TAG}"

if [[ "$PRINT_ONLY" -eq 1 ]]; then
  echo "$CRON_LINE"
  exit 0
fi

if ! command -v crontab >/dev/null 2>&1; then
  echo "crontab command not found" >&2
  exit 1
fi

TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

if crontab -l >/dev/null 2>&1; then
  crontab -l | grep -v "WOOHWAHAE_PIPELINE_RESILIENCE" >"$TMP_FILE" || true
fi

echo "$CRON_LINE" >>"$TMP_FILE"
crontab "$TMP_FILE"

echo "[pipeline-resilience-cron] installed"
crontab -l | grep "WOOHWAHAE_PIPELINE_RESILIENCE" || true

