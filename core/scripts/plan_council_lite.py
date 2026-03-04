"""
Offline fallback when Plan Council (Claude/Gemini) is unreachable.

Generates a minimal plan payload and appends to plan_council_reports.jsonl
with status "degraded-lite" so downstream tooling can trace provenance.

This does NOT call external models. Use only when official Plan Council
returns HARD STOP due to availability.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "knowledge/system/plan_council_reports.jsonl"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def build_payload(task: str) -> dict:
    return {
        "timestamp": now_iso(),
        "mode": "preflight-lite",
        "task": task,
        "consensus": {
            "status": "degraded-lite",
            "models_used": [],
            "planner_primary": "offline",
            "verifier_secondary": "offline",
            "intent": task,
            "approach": "offline fallback; no external models available",
            "steps": [
                "Load AGENTS.md + CLAUDE.md guardrails",
                "Run python3 core/system/evidence_guard.py --check",
                "If web work: acquire lock via web_consistency_lock.py",
                "List impacts/risks before file writes",
                "Run relevant validators/tests before handoff",
            ],
            "risks": [
                "Plan Council unavailable; assumptions may miss edge cases",
                "No dual-model disagreement signal",
            ],
            "checks": [
                "Document fallback in reports.jsonl",
                "Re-run official Plan Council when connectivity restored",
            ],
            "decision": "go",
        },
    }


def append_report(payload: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False))
        f.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan Council offline fallback")
    parser.add_argument("--task", required=True)
    parser.add_argument("--json", action="store_true", help="print payload json")
    args = parser.parse_args()

    payload = build_payload(args.task)
    append_report(payload)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("status: degraded-lite (offline plan logged)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
