#!/usr/bin/env python3
"""Minimal alert checker for payment webhook errors."""

from __future__ import annotations

import argparse
import json
import re
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
    return parser.parse_args()


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
