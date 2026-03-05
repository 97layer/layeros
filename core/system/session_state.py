#!/usr/bin/env python3
"""
Session state updater for knowledge/system/system_state.json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYSTEM_STATE_PATH = PROJECT_ROOT / "knowledge" / "system" / "system_state.json"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def infer_session_id(agent_id: str) -> str:
    return f"{agent_id.lower()}-{os.getpid()}-{int(datetime.now().timestamp())}"


def find_latest_session_id(sessions: Dict[str, Any], agent_id: str) -> Optional[str]:
    best_sid: Optional[str] = None
    best_ts = ""
    for sid, payload in sessions.items():
        if not isinstance(payload, dict):
            continue
        if str(payload.get("agent_id", "")) != agent_id:
            continue
        updated_at = str(payload.get("updated_at", ""))
        if updated_at >= best_ts:
            best_ts = updated_at
            best_sid = sid
    return best_sid


def cmd_start(args: argparse.Namespace) -> int:
    state = load_state(SYSTEM_STATE_PATH)
    sessions = state.setdefault("sessions", {})
    if not isinstance(sessions, dict):
        sessions = {}
        state["sessions"] = sessions

    session_id = (args.session_id or "").strip() or infer_session_id(args.agent_id)
    ts_iso = now_iso()
    sessions[session_id] = {
        "agent_id": args.agent_id,
        "task_label": args.task_label,
        "status": "active",
        "started_at": sessions.get(session_id, {}).get("started_at", ts_iso)
        if isinstance(sessions.get(session_id), dict)
        else ts_iso,
        "updated_at": ts_iso,
        "summary": "",
    }
    state["last_update"] = now_stamp()
    save_state(SYSTEM_STATE_PATH, state)
    print(session_id)
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    state = load_state(SYSTEM_STATE_PATH)
    sessions = state.setdefault("sessions", {})
    if not isinstance(sessions, dict):
        sessions = {}
        state["sessions"] = sessions

    session_id = (args.session_id or "").strip()
    if not session_id:
        session_id = find_latest_session_id(sessions, args.agent_id) or infer_session_id(args.agent_id)

    existing = sessions.get(session_id, {})
    if not isinstance(existing, dict):
        existing = {}
    ts_iso = now_iso()
    sessions[session_id] = {
        "agent_id": args.agent_id,
        "task_label": args.task_label or str(existing.get("task_label", "")),
        "status": "completed",
        "started_at": str(existing.get("started_at", ts_iso)),
        "updated_at": ts_iso,
        "summary": args.summary,
    }
    state["last_update"] = now_stamp()
    save_state(SYSTEM_STATE_PATH, state)
    print(session_id)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update system_state session activity")
    parser.add_argument("--event", choices=["start", "finish"], required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--task-label", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--summary", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.event == "start":
        return cmd_start(args)
    return cmd_finish(args)


if __name__ == "__main__":
    raise SystemExit(main())
