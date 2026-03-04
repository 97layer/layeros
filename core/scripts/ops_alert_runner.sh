#!/usr/bin/env bash
# Cron-safe runner for ops alert check.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

if [[ -f .env ]]; then
  eval "$(
    python3 core/scripts/safe_env_export.py --file .env --keys \
      TELEGRAM_BOT_TOKEN \
      ADMIN_TELEGRAM_ID \
      TELEGRAM_CHAT_ID \
      OPS_SLACK_WEBHOOK_URL \
      OPS_ALERT_LOG_FILE \
      OPS_ALERT_WEBHOOK_5XX_THRESHOLD \
      OPS_ALERT_COMMIT_FAIL_THRESHOLD \
      OPS_ALERT_COOLDOWN_FILE \
      OPS_ALERT_COOLDOWN_SECONDS
  )"
fi

LOG_FILE="${OPS_ALERT_LOG_FILE:-.infra/logs/woohwahae-gateway.log}"
WEBHOOK_5XX_THRESHOLD="${OPS_ALERT_WEBHOOK_5XX_THRESHOLD:-3}"
COMMIT_FAIL_THRESHOLD="${OPS_ALERT_COMMIT_FAIL_THRESHOLD:-1}"
COOLDOWN_FILE="${OPS_ALERT_COOLDOWN_FILE:-knowledge/system/ops_alert_cooldown.json}"
COOLDOWN_SECONDS="${OPS_ALERT_COOLDOWN_SECONDS:-900}"

python3 core/scripts/ops_alert_check.py \
  --log-file "$LOG_FILE" \
  --webhook-5xx-threshold "$WEBHOOK_5XX_THRESHOLD" \
  --commit-fail-threshold "$COMMIT_FAIL_THRESHOLD" \
  --cooldown-file "$COOLDOWN_FILE" \
  --cooldown-seconds "$COOLDOWN_SECONDS" \
  --notify \
  "$@"
