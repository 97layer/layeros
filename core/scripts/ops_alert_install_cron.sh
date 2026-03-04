#!/usr/bin/env bash
# Install/update cron entry for ops alert runner.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

SCHEDULE="*/5 * * * *"
PRINT_ONLY=0

usage() {
  cat <<'EOF'
Usage:
  bash core/scripts/ops_alert_install_cron.sh [options]

Options:
  --schedule "CRON"   Cron schedule (default: */5 * * * *)
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

RUNNER_CMD="/bin/bash -lc 'cd ${PROJECT_ROOT} && ./core/scripts/ops_alert_runner.sh >> /tmp/woohwahae-ops-alert.log 2>&1'"
CRON_TAG="# WOOHWAHAE_OPS_ALERT"
CRON_LINE="${SCHEDULE} ${RUNNER_CMD} ${CRON_TAG}"

install_systemd_timer() {
  local interval_min="5"
  if [[ "$SCHEDULE" =~ ^\*/([0-9]+)[[:space:]]+\*[[:space:]]+\*[[:space:]]+\*[[:space:]]+\*$ ]]; then
    interval_min="${BASH_REMATCH[1]}"
  fi

  local service_name="woohwahae-ops-alert"
  local run_user
  run_user="$(id -un)"

  if [[ "$PRINT_ONLY" -eq 1 ]]; then
    echo "[print-only] systemd timer fallback"
    echo "[print-only] interval=${interval_min}min user=${run_user}"
    echo "[print-only] service=/etc/systemd/system/${service_name}.service"
    echo "[print-only] timer=/etc/systemd/system/${service_name}.timer"
    return
  fi

  sudo tee "/etc/systemd/system/${service_name}.service" >/dev/null <<EOF
[Unit]
Description=WOOHWAHAE Ops Alert Runner
After=network.target

[Service]
Type=oneshot
User=${run_user}
WorkingDirectory=${PROJECT_ROOT}
ExecStart=/bin/bash -lc 'cd ${PROJECT_ROOT} && ./core/scripts/ops_alert_runner.sh'
StandardOutput=append:/tmp/woohwahae-ops-alert.log
StandardError=append:/tmp/woohwahae-ops-alert.log
EOF

  sudo tee "/etc/systemd/system/${service_name}.timer" >/dev/null <<EOF
[Unit]
Description=WOOHWAHAE Ops Alert Timer

[Timer]
OnBootSec=2min
OnUnitActiveSec=${interval_min}min
AccuracySec=30s
Persistent=true
Unit=${service_name}.service

[Install]
WantedBy=timers.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable --now "${service_name}.timer"

  echo "[ops-alert-timer] installed"
  sudo systemctl is-active "${service_name}.timer"
  sudo systemctl list-timers --all "${service_name}.timer" --no-pager
}

if [[ "$PRINT_ONLY" -eq 1 ]]; then
  echo "$CRON_LINE"
  exit 0
fi

TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

if ! command -v crontab >/dev/null 2>&1; then
  install_systemd_timer
  exit 0
fi

if crontab -l >/dev/null 2>&1; then
  crontab -l | grep -v "WOOHWAHAE_OPS_ALERT" >"$TMP_FILE" || true
fi

echo "$CRON_LINE" >>"$TMP_FILE"
crontab "$TMP_FILE"

echo "[ops-alert-cron] installed"
crontab -l | grep "WOOHWAHAE_OPS_ALERT" || true
