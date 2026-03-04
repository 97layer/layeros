#!/usr/bin/env bash
# One-command rollback helper for /admin route target.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

TARGET="legacy"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  bash core/scripts/ops_rollback.sh [options]

Options:
  --to legacy|gateway   Route target (default: legacy)
  --dry-run             Print commands only
  -h, --help            Show help

Examples:
  bash core/scripts/ops_rollback.sh
  bash core/scripts/ops_rollback.sh --to gateway
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --to)
      TARGET="${2:-legacy}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
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

if [[ "$TARGET" != "legacy" && "$TARGET" != "gateway" ]]; then
  echo "Invalid target: ${TARGET}. Use legacy or gateway." >&2
  exit 1
fi

SWITCH_CMD=(bash core/scripts/deploy/deploy.sh admin-route-switch "$TARGET")
STATUS_CMD=(bash core/scripts/deploy/deploy.sh admin-route-status)
GATEWAY_STATUS_CMD=(bash core/scripts/deploy/deploy.sh gateway-status)

cd "$PROJECT_ROOT"

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf '[dry-run] %q ' "${SWITCH_CMD[@]}"
  printf '\n'
  printf '[dry-run] %q ' "${STATUS_CMD[@]}"
  printf '\n'
  printf '[dry-run] %q ' "${GATEWAY_STATUS_CMD[@]}"
  printf '\n'
  exit 0
fi

echo "[ops-rollback] switch /admin route -> ${TARGET}"
"${SWITCH_CMD[@]}"
echo "[ops-rollback] route status"
"${STATUS_CMD[@]}"
echo "[ops-rollback] gateway status"
"${GATEWAY_STATUS_CMD[@]}"
echo "[ops-rollback] DONE"
