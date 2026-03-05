#!/usr/bin/env python3
"""
plan_dispatch_pending_replay 단위/통합 테스트
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPLAY_SCRIPT = PROJECT_ROOT / "core" / "scripts" / "plan_dispatch_pending_replay.py"
MODULE_SPEC = importlib.util.spec_from_file_location("plan_dispatch_pending_replay", REPLAY_SCRIPT)
assert MODULE_SPEC and MODULE_SPEC.loader
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MODULE)
build_open_pending = MODULE.build_open_pending
classify_status = MODULE.classify_status
compact_pending_rows = MODULE.compact_pending_rows


def _iso(offset_sec: int) -> str:
    base = datetime(2026, 3, 4, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_sec)).isoformat()


def test_build_open_pending_filters_resolved_and_non_retryable():
    pending_rows = [
        {
            "timestamp": _iso(10),
            "task_hash": "aaa111",
            "task": "task-1",
            "retryable": True,
        },
        {
            "timestamp": _iso(20),
            "task_hash": "bbb222",
            "task": "task-2",
            "retryable": False,
        },
        {
            "timestamp": _iso(30),
            "task_hash": "ccc333",
            "task": "task-3",
            "retryable": True,
        },
    ]
    result_rows = [
        {"timestamp": _iso(40), "task_hash": "aaa111", "status": "resolved"},
        {"timestamp": _iso(41), "task_hash": "ccc333", "status": "blocked"},
    ]

    open_rows = build_open_pending(pending_rows, result_rows)
    assert len(open_rows) == 1
    assert open_rows[0]["task_hash"] == "ccc333"


def test_classify_status_mapping():
    assert classify_status(0, {"dispatcher": {"reason": "executed"}}) == "resolved"
    assert classify_status(2, {"dispatcher": {"reason": "needs_clarification_model"}}) == "ignored"
    assert classify_status(3, {"dispatcher": {"reason": "hard_stop_fallback_lite"}}) == "blocked_lite"
    assert classify_status(3, {"dispatcher": {"reason": "runtime_caution_not_allowed"}}) == "blocked"


def test_compact_pending_rows_removes_resolved_and_ignored():
    pending_rows = [
        {"timestamp": _iso(10), "task_hash": "aaa111", "task": "task-1"},
        {"timestamp": _iso(20), "task_hash": "bbb222", "task": "task-2"},
        {"timestamp": _iso(30), "task_hash": "ccc333", "task": "task-3"},
    ]
    result_rows = [
        {"timestamp": _iso(40), "task_hash": "aaa111", "status": "resolved"},
        {"timestamp": _iso(41), "task_hash": "bbb222", "status": "ignored"},
        {"timestamp": _iso(25), "task_hash": "ccc333", "status": "resolved"},
    ]
    kept, removed = compact_pending_rows(pending_rows, result_rows)
    assert removed == 2
    assert [row["task_hash"] for row in kept] == ["ccc333"]


def test_pending_replay_cli_resolves_with_fake_dispatch(tmp_path: Path):
    pending_log = tmp_path / "pending.jsonl"
    result_log = tmp_path / "results.jsonl"
    now_ts = datetime.now(timezone.utc).isoformat()
    pending_entry = {
        "timestamp": now_ts,
        "task_hash": "ddd444",
        "task_preview": "retry target",
        "task": "retry target full task",
        "reason": "hard_stop_model_unavailable",
        "retryable": True,
    }
    pending_log.write_text(json.dumps(pending_entry, ensure_ascii=False) + "\n", encoding="utf-8")

    fake_dispatch = tmp_path / "fake_plan_dispatch.sh"
    fake_dispatch.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "task=\"$1\"",
                "echo \"{\\\"dispatcher\\\":{\\\"reason\\\":\\\"executed\\\"},\\\"consensus\\\":{\\\"status\\\":\\\"ready\\\"},\\\"task\\\":\\\"${task}\\\"}\"",
                "exit 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PLAN_DISPATCH_REPLAY_SCRIPT"] = str(fake_dispatch)
    proc = subprocess.run(
        [
            "python3",
            str(REPLAY_SCRIPT),
            "--pending-log",
            str(pending_log),
            "--result-log",
            str(result_log),
            "--json",
            "--limit",
            "5",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["summary"]["resolved"] == 1
    assert result_log.exists()
    row = json.loads(result_log.read_text(encoding="utf-8").splitlines()[-1])
    assert row["status"] == "resolved"
    pending_after = [line for line in pending_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert pending_after == []


def test_pending_replay_drop_stale_marks_ignored_and_compacts(tmp_path: Path):
    pending_log = tmp_path / "pending_stale.jsonl"
    result_log = tmp_path / "results_stale.jsonl"
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    pending_entry = {
        "timestamp": stale_ts,  # old enough to exceed max-age-hours=1
        "task_hash": "stale001",
        "task_preview": "stale target",
        "task": "stale target full task",
        "reason": "hard_stop_model_unavailable",
        "retryable": True,
    }
    pending_log.write_text(json.dumps(pending_entry, ensure_ascii=False) + "\n", encoding="utf-8")

    proc = subprocess.run(
        [
            "python3",
            str(REPLAY_SCRIPT),
            "--pending-log",
            str(pending_log),
            "--result-log",
            str(result_log),
            "--drop-stale",
            "--max-age-hours",
            "1",
            "--json",
            "--limit",
            "3",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["summary"]["ignored"] == 1
    assert payload["summary"]["dropped_stale"] == 1
    result_rows = [line for line in result_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert result_rows
    row = json.loads(result_rows[-1])
    assert row["status"] == "ignored"
    assert row["reason"] == "stale_age_exceeded"
    pending_after = [line for line in pending_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert pending_after == []
