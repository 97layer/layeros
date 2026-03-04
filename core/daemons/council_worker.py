#!/usr/bin/env python3
"""
Council Worker — Plan Council 비동기 처리 데몬
pending 큐(.infra/queue/council/pending) → processing → completed
결과: knowledge/system/plan_council_reports.jsonl, knowledge/agent_hub/council_room.md append
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.system.plan_council import run_council  # 계획 합의 실행기
import requests

QUEUE_ROOT = PROJECT_ROOT / ".infra/queue/council"
PENDING = QUEUE_ROOT / "pending"
PROCESSING = QUEUE_ROOT / "processing"
COMPLETED = QUEUE_ROOT / "completed"

REPORTS = PROJECT_ROOT / "knowledge/system/plan_council_reports.jsonl"
COUNCIL_ROOM = PROJECT_ROOT / "knowledge/agent_hub/council_room.md"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
_WARNED_NO_TELEGRAM = False


def load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except Exception:
        pass


def safe_move(src: Path, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    src.rename(dst)
    return dst


def append_report(entry: Dict):
    REPORTS.parent.mkdir(parents=True, exist_ok=True)
    with REPORTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def append_council_room(entry: Dict):
    COUNCIL_ROOM.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append(f"## [{entry['timestamp']}] Council 협의 — {entry['task']}")
    lines.append("")
    lines.append(f"**proposal_id**: `{entry['proposal_id']}`  **신호**: 1개 (비동기 큐)")
    lines.append("")
    lines.append(f"**status**: {entry['status']}  **gate**: {entry.get('gate','')}")
    lines.append("")
    lines.append(f"**steps**: {entry.get('steps','')}")
    lines.append("")
    lines.append("---")
    lines.append("")
    with COUNCIL_ROOM.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def notify_telegram(entry: Dict):
    global _WARNED_NO_TELEGRAM
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        if not _WARNED_NO_TELEGRAM:
            print("[council_worker] TELEGRAM_* env missing — notifications skipped", file=sys.stderr)
            _WARNED_NO_TELEGRAM = True
        return
    text = (
        f"[Council] {entry['task']}\n"
        f"status: {entry['status']} gate: {entry.get('gate','')}\n"
        f"models: {', '.join(entry.get('models_used', []))}"
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=5,
        )
    except Exception:
        pass


def process_task(task_path: Path):
    data = json.loads(task_path.read_text(encoding="utf-8"))
    intent = data.get("intent") or data.get("task") or "unspecified task"

    res = run_council(intent, mode="preflight", require_both=True, silent=True)
    now = datetime.utcnow().isoformat()
    entry = {
        "timestamp": now,
        "proposal_id": data.get("proposal_id", task_path.stem),
        "task": intent,
        "status": res.status,
        "gate": res.gate,
        "steps": res.steps,
        "risks": res.risks,
        "checks": res.checks,
        "models_used": res.models_used,
    }
    append_report(entry)
    append_council_room(entry)


def main():
    load_env()
    PENDING.mkdir(parents=True, exist_ok=True)
    for task_path in sorted(PENDING.glob("*.json")):
        proc_path = safe_move(task_path, PROCESSING)
        try:
            process_task(proc_path)
            safe_move(proc_path, COMPLETED)
        except Exception as e:
            # 실패 시 다시 pending으로 되돌려 재시도
            safe_move(proc_path, PENDING)
            print(f"[council_worker] error: {proc_path.name} — {e}", file=sys.stderr)
        time.sleep(0.2)  # rate limit 보호


if __name__ == "__main__":
    main()
