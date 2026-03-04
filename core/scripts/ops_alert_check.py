#!/usr/bin/env python3
"""Minimal alert checker for payment webhook errors."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


WEBHOOK_5XX_PATTERN = re.compile(
    r"(?:/api/v1/payments/webhook|/payments/webhook).*(?:\s|=|:)(5\d\d)\b"
)
COMMIT_FAIL_PATTERN = re.compile(r"Database commit failed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check webhook 5xx and Database commit failed signals from log file."
    )
    parser.add_argument(
        "--log-file",
        default=".infra/logs/woohwahae-gateway.log",
        help="Path to gateway log file (default: .infra/logs/woohwahae-gateway.log)",
    )
    parser.add_argument(
        "--tail-lines",
        type=int,
        default=4000,
        help="Number of recent lines to inspect (default: 4000)",
    )
    parser.add_argument(
        "--webhook-5xx-threshold",
        type=int,
        default=3,
        help="Alert threshold for webhook 5xx count (default: 3)",
    )
    parser.add_argument(
        "--commit-fail-threshold",
        type=int,
        default=1,
        help="Alert threshold for 'Database commit failed' count (default: 1)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send notifications when alert is triggered",
    )
    parser.add_argument(
        "--telegram-token-env",
        default="TELEGRAM_BOT_TOKEN",
        help="Env var name for telegram bot token (default: TELEGRAM_BOT_TOKEN)",
    )
    parser.add_argument(
        "--telegram-chat-env",
        default="ADMIN_TELEGRAM_ID",
        help="Primary env var name for telegram chat id (default: ADMIN_TELEGRAM_ID)",
    )
    parser.add_argument(
        "--telegram-chat-fallback-env",
        default="TELEGRAM_CHAT_ID",
        help="Fallback env var for telegram chat id (default: TELEGRAM_CHAT_ID)",
    )
    parser.add_argument(
        "--slack-webhook-env",
        default="OPS_SLACK_WEBHOOK_URL",
        help="Env var name for Slack incoming webhook URL (default: OPS_SLACK_WEBHOOK_URL)",
    )
    parser.add_argument(
        "--cooldown-file",
        default="knowledge/system/ops_alert_cooldown.json",
        help="Cooldown file to prevent duplicate notifications",
    )
    parser.add_argument(
        "--cooldown-seconds",
        type=int,
        default=900,
        help="Notification cooldown in seconds (default: 900)",
    )
    return parser.parse_args()


def _post_json(url: str, payload: dict) -> None:
    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8):  # noqa: S310
        return


def _send_telegram(text: str, token: str, chat_id: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    _post_json(url, {"chat_id": chat_id, "text": text})


def _send_slack(text: str, webhook_url: str) -> None:
    _post_json(webhook_url, {"text": text})


def _build_alert_message(payload: dict) -> str:
    counts = payload.get("counts", {})
    thresholds = payload.get("thresholds", {})
    return (
        "[ops-alert] ALERT\n"
        f"- webhook_5xx: {counts.get('webhook_5xx', 0)} / {thresholds.get('webhook_5xx', 0)}\n"
        f"- db_commit_failed: {counts.get('db_commit_failed', 0)} / {thresholds.get('db_commit_failed', 0)}\n"
        f"- log: {payload.get('log_file')}"
    )


def _should_notify(payload: dict, cooldown_file: Path, cooldown_seconds: int) -> bool:
    alerts = payload.get("alerts", [])
    counts = payload.get("counts", {})
    signature = (
        f"{','.join(sorted(alerts))}|"
        f"{counts.get('webhook_5xx', 0)}|{counts.get('db_commit_failed', 0)}"
    )
    now = int(time.time())

    previous = {}
    if cooldown_file.exists():
        try:
            previous = json.loads(cooldown_file.read_text(encoding="utf-8"))
        except Exception:
            previous = {}

    last_signature = str(previous.get("signature", ""))
    last_notified_at = int(previous.get("notified_at", 0))
    is_cooling_down = (
        last_signature == signature and now - last_notified_at < max(0, cooldown_seconds)
    )
    if is_cooling_down:
        return False

    cooldown_file.parent.mkdir(parents=True, exist_ok=True)
    cooldown_file.write_text(
        json.dumps({"signature": signature, "notified_at": now}, ensure_ascii=False),
        encoding="utf-8",
    )
    return True


def main() -> int:
    args = parse_args()
    log_file = Path(args.log_file)
    if not log_file.exists():
        message = {
            "status": "missing_log",
            "log_file": str(log_file),
        }
        if args.json:
            print(json.dumps(message, ensure_ascii=False))
        else:
            print(f"[ops-alert] log file not found: {log_file}")
        return 2

    lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    if args.tail_lines > 0:
        lines = lines[-args.tail_lines :]

    webhook_5xx_count = 0
    commit_fail_count = 0

    for line in lines:
        if WEBHOOK_5XX_PATTERN.search(line):
            webhook_5xx_count += 1
        if COMMIT_FAIL_PATTERN.search(line):
            commit_fail_count += 1

    alerts: list[str] = []
    if webhook_5xx_count >= args.webhook_5xx_threshold:
        alerts.append("webhook_5xx")
    if commit_fail_count >= args.commit_fail_threshold:
        alerts.append("db_commit_failed")

    payload = {
        "status": "alert" if alerts else "ok",
        "log_file": str(log_file),
        "tail_lines": args.tail_lines,
        "counts": {
            "webhook_5xx": webhook_5xx_count,
            "db_commit_failed": commit_fail_count,
        },
        "thresholds": {
            "webhook_5xx": args.webhook_5xx_threshold,
            "db_commit_failed": args.commit_fail_threshold,
        },
        "alerts": alerts,
    }

    notifications: list[str] = []
    if args.notify and alerts:
        cooldown_path = Path(args.cooldown_file)
        should_notify = _should_notify(payload, cooldown_path, args.cooldown_seconds)
        if should_notify:
            message = _build_alert_message(payload)
            token = os.getenv(args.telegram_token_env, "").strip()
            chat_id = os.getenv(args.telegram_chat_env, "").strip() or os.getenv(
                args.telegram_chat_fallback_env, ""
            ).strip()
            slack_webhook = os.getenv(args.slack_webhook_env, "").strip()

            if token and chat_id:
                try:
                    _send_telegram(message, token=token, chat_id=chat_id)
                    notifications.append("telegram")
                except (urllib.error.URLError, ValueError):
                    notifications.append("telegram_failed")

            if slack_webhook:
                try:
                    _send_slack(message, webhook_url=slack_webhook)
                    notifications.append("slack")
                except (urllib.error.URLError, ValueError):
                    notifications.append("slack_failed")
        else:
            notifications.append("cooldown")

    if notifications:
        payload["notifications"] = notifications

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"[ops-alert] webhook_5xx={webhook_5xx_count} threshold={args.webhook_5xx_threshold}")
        print(
            "[ops-alert] db_commit_failed="
            f"{commit_fail_count} threshold={args.commit_fail_threshold}"
        )
        if alerts:
            print(f"[ops-alert] ALERT: {', '.join(alerts)}")
        else:
            print("[ops-alert] OK")

    return 1 if alerts else 0


if __name__ == "__main__":
    raise SystemExit(main())
