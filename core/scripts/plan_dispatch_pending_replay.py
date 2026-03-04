#!/usr/bin/env python3
"""
Replay unresolved plan_dispatch blocked tasks from pending queue log.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PENDING_LOG = PROJECT_ROOT / "knowledge" / "system" / "plan_dispatch_pending.jsonl"
DEFAULT_RESULT_LOG = PROJECT_ROOT / "knowledge" / "system" / "plan_dispatch_pending_results.jsonl"
DEFAULT_LOCK_PATH = PROJECT_ROOT / "knowledge" / "system" / "plan_dispatch_pending.lock"
PLAN_DISPATCH_SCRIPT = Path(
    os.getenv(
        "PLAN_DISPATCH_REPLAY_SCRIPT",
        str(PROJECT_ROOT / "core" / "scripts" / "plan_dispatch.sh"),
    )
)
try:
    import fcntl as _fcntl  # POSIX only
except Exception:  # pragma: no cover - non-POSIX fallback
    _fcntl = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


@contextmanager
def file_lock(lock_path: Path, timeout_sec: float) -> Any:
    """
    Cooperative file lock for multi-agent sessions.
    Falls back to no-op lock when fcntl is unavailable.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fp = lock_path.open("a+", encoding="utf-8")
    if _fcntl is None:  # pragma: no cover
        try:
            yield
        finally:
            fp.close()
        return

    deadline = time.time() + max(0.1, float(timeout_sec))
    locked = False
    while not locked:
        try:
            _fcntl.flock(fp.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            locked = True
        except BlockingIOError:
            if time.time() >= deadline:
                fp.close()
                raise TimeoutError(f"pending lock timeout: {lock_path}")
            time.sleep(0.05)

    try:
        yield
    finally:
        try:
            _fcntl.flock(fp.fileno(), _fcntl.LOCK_UN)
        finally:
            fp.close()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def overwrite_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_jsonl_rows(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_epoch(timestamp: Any) -> float:
    text = str(timestamp or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def age_hours(timestamp: Any, *, now_epoch: float | None = None) -> float:
    ts = parse_epoch(timestamp)
    if ts <= 0:
        return 0.0
    current = now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp()
    delta = max(0.0, current - ts)
    return delta / 3600.0


def split_by_age(
    open_rows: List[Dict[str, Any]],
    *,
    max_age_hours: float,
    now_epoch: float | None = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if max_age_hours <= 0:
        return list(open_rows), []

    active: List[Dict[str, Any]] = []
    stale: List[Dict[str, Any]] = []
    for row in open_rows:
        row_age = age_hours(row.get("timestamp"), now_epoch=now_epoch)
        if row_age > max_age_hours:
            stale.append(row)
        else:
            active.append(row)
    return active, stale


def oldest_age_hours(rows: List[Dict[str, Any]], *, now_epoch: float | None = None) -> float:
    if not rows:
        return 0.0
    return max(age_hours(row.get("timestamp"), now_epoch=now_epoch) for row in rows)


def compact_pending_rows(
    pending_rows: List[Dict[str, Any]],
    result_rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    latest_result: Dict[str, Dict[str, Any]] = {}
    for row in result_rows:
        task_hash = str(row.get("task_hash", "")).strip()
        if not task_hash:
            continue
        row_epoch = parse_epoch(row.get("timestamp"))
        prev = latest_result.get(task_hash)
        prev_epoch = parse_epoch(prev.get("timestamp")) if isinstance(prev, dict) else 0.0
        if prev is None or row_epoch >= prev_epoch:
            latest_result[task_hash] = row

    kept: List[Dict[str, Any]] = []
    removed = 0
    for row in pending_rows:
        task_hash = str(row.get("task_hash", "")).strip()
        if not task_hash:
            kept.append(row)
            continue

        pending_epoch = parse_epoch(row.get("timestamp"))
        result = latest_result.get(task_hash)
        if not isinstance(result, dict):
            kept.append(row)
            continue

        status = str(result.get("status", "")).strip().lower()
        result_epoch = parse_epoch(result.get("timestamp"))
        if status in {"resolved", "ignored"} and result_epoch >= pending_epoch:
            removed += 1
            continue
        kept.append(row)
    return kept, removed


def build_open_pending(
    pending_rows: List[Dict[str, Any]],
    result_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    pending_latest: Dict[str, Dict[str, Any]] = {}
    for row in pending_rows:
        task_hash = str(row.get("task_hash", "")).strip()
        if not task_hash:
            continue
        row_epoch = parse_epoch(row.get("timestamp"))
        prev = pending_latest.get(task_hash)
        prev_epoch = parse_epoch(prev.get("timestamp")) if isinstance(prev, dict) else 0.0
        if prev is None or row_epoch >= prev_epoch:
            pending_latest[task_hash] = row

    result_latest: Dict[str, Dict[str, Any]] = {}
    for row in result_rows:
        task_hash = str(row.get("task_hash", "")).strip()
        if not task_hash:
            continue
        row_epoch = parse_epoch(row.get("timestamp"))
        prev = result_latest.get(task_hash)
        prev_epoch = parse_epoch(prev.get("timestamp")) if isinstance(prev, dict) else 0.0
        if prev is None or row_epoch >= prev_epoch:
            result_latest[task_hash] = row

    open_items: List[Dict[str, Any]] = []
    for task_hash, pending in pending_latest.items():
        retryable = bool(pending.get("retryable", True))
        if not retryable:
            continue
        pending_epoch = parse_epoch(pending.get("timestamp"))
        result = result_latest.get(task_hash)
        if isinstance(result, dict):
            status = str(result.get("status", "")).strip().lower()
            result_epoch = parse_epoch(result.get("timestamp"))
            if status in {"resolved", "ignored"} and result_epoch >= pending_epoch:
                continue
        open_items.append(pending)

    open_items.sort(key=lambda item: parse_epoch(item.get("timestamp")))
    return open_items


def parse_dispatch_payload(stdout: str) -> Dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def classify_status(returncode: int, payload: Dict[str, Any]) -> str:
    dispatcher = payload.get("dispatcher")
    reason = ""
    if isinstance(dispatcher, dict):
        reason = str(dispatcher.get("reason", "")).strip().lower()

    if returncode == 0:
        return "resolved"
    if returncode == 2:
        return "ignored"
    if returncode == 3 and reason == "hard_stop_fallback_lite":
        return "blocked_lite"
    if returncode in {1, 3}:
        return "blocked"
    return "error"


def replay_task(
    entry: Dict[str, Any],
    *,
    mode: str,
    allow_degraded: bool,
    auto_lite_fallback: bool,
    council_retries: int,
) -> Tuple[int, Dict[str, Any], str]:
    task = str(entry.get("task", "")).strip()
    if not task:
        return 2, {}, "missing task"

    cmd = ["bash", str(PLAN_DISPATCH_SCRIPT), task, f"--{mode}"]
    env = os.environ.copy()
    env["PLAN_DISPATCH_LOG_PENDING"] = "0"
    if allow_degraded:
        env["PLAN_DISPATCH_ALLOW_DEGRADED"] = "1"
    if auto_lite_fallback:
        env["PLAN_DISPATCH_AUTO_LITE_FALLBACK"] = "1"
    if council_retries > 0:
        env["PLAN_DISPATCH_COUNCIL_RETRIES"] = str(council_retries)

    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    payload = parse_dispatch_payload(proc.stdout)
    stderr_tail = "\n".join((proc.stderr or "").splitlines()[-4:])
    return proc.returncode, payload, stderr_tail


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay unresolved plan_dispatch pending queue")
    parser.add_argument("--pending-log", default=str(DEFAULT_PENDING_LOG), help="pending jsonl path")
    parser.add_argument("--result-log", default=str(DEFAULT_RESULT_LOG), help="replay result jsonl path")
    parser.add_argument(
        "--lock-path",
        default=os.getenv("PLAN_DISPATCH_PENDING_LOCK", str(DEFAULT_LOCK_PATH)),
        help="cooperative lock file path for pending/result logs",
    )
    parser.add_argument(
        "--lock-timeout-sec",
        type=float,
        default=_env_float("PLAN_DISPATCH_PENDING_LOCK_TIMEOUT", 30.0),
        help="lock wait timeout in seconds",
    )
    parser.add_argument("--limit", type=int, default=10, help="max pending entries to replay")
    parser.add_argument("--mode", choices=["auto", "manual"], default="auto", help="dispatch mode")
    parser.add_argument("--allow-degraded", action="store_true", help="set PLAN_DISPATCH_ALLOW_DEGRADED=1")
    parser.add_argument(
        "--auto-lite-fallback",
        action="store_true",
        help="set PLAN_DISPATCH_AUTO_LITE_FALLBACK=1 while replaying",
    )
    parser.add_argument("--council-retries", type=int, default=1, help="override PLAN_DISPATCH_COUNCIL_RETRIES")
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=_env_float("PLAN_DISPATCH_PENDING_MAX_AGE_HOURS", 24.0),
        help="stale pending cutoff age in hours (<=0 disables age filter)",
    )
    parser.add_argument(
        "--drop-stale",
        action="store_true",
        help="write stale pending tasks into result log as ignored",
    )
    parser.set_defaults(compact_pending=_env_bool("PLAN_DISPATCH_PENDING_COMPACT", True))
    parser.add_argument(
        "--compact-pending",
        dest="compact_pending",
        action="store_true",
        help="remove terminal( resolved/ignored ) items from pending log after replay",
    )
    parser.add_argument(
        "--no-compact-pending",
        dest="compact_pending",
        action="store_false",
        help="do not compact pending log",
    )
    parser.add_argument("--dry-run", action="store_true", help="list replay candidates only")
    parser.add_argument("--json", action="store_true", help="print JSON payload")
    args = parser.parse_args()

    pending_log = Path(args.pending_log)
    result_log = Path(args.result_log)
    lock_path = Path(args.lock_path)
    lock_timeout = max(0.1, float(args.lock_timeout_sec))

    with file_lock(lock_path, lock_timeout):
        pending_rows = load_jsonl(pending_log)
        result_rows = load_jsonl(result_log)
    open_rows = build_open_pending(pending_rows, result_rows)
    now_epoch = datetime.now(timezone.utc).timestamp()
    max_age_hours = max(0.0, float(args.max_age_hours))
    open_retryable_rows, stale_rows = split_by_age(
        open_rows,
        max_age_hours=max_age_hours,
        now_epoch=now_epoch,
    )
    oldest_open_age = oldest_age_hours(open_retryable_rows, now_epoch=now_epoch)
    oldest_stale_age = oldest_age_hours(stale_rows, now_epoch=now_epoch)
    limit = max(1, int(args.limit))
    targets = open_retryable_rows[:limit]

    payload: Dict[str, Any] = {
        "timestamp": now_iso(),
        "pending_log": str(pending_log),
        "result_log": str(result_log),
        "pending_total": len(pending_rows),
        "open_total": len(open_rows),
        "open_retryable_total": len(open_retryable_rows),
        "stale_total": len(stale_rows),
        "dropped_stale": 0,
        "max_age_hours": max_age_hours,
        "oldest_open_age_hours": round(oldest_open_age, 3),
        "oldest_stale_age_hours": round(oldest_stale_age, 3),
        "selected": len(targets),
        "mode": args.mode,
        "dry_run": bool(args.dry_run),
        "compact_pending": bool(args.compact_pending),
        "lock_path": str(lock_path),
        "results": [],
    }

    if args.dry_run:
        payload["results"] = [
            {
                "task_hash": row.get("task_hash", ""),
                "reason": row.get("reason", ""),
                "complexity": row.get("complexity", ""),
                "timestamp": row.get("timestamp", ""),
                "task_preview": row.get("task_preview", ""),
            }
            for row in targets
        ]
        payload["summary"] = {
            "resolved": 0,
            "blocked": 0,
            "ignored": 0,
            "error": 0,
            "stale_total": len(stale_rows),
            "dropped_stale": 0,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(
                f"open_total={payload['open_total']} "
                f"retryable={payload['open_retryable_total']} "
                f"stale={payload['stale_total']} selected={payload['selected']}"
            )
        return 0

    counts = {"resolved": 0, "blocked": 0, "ignored": 0, "error": 0}
    new_result_rows: List[Dict[str, Any]] = []
    if args.drop_stale and stale_rows:
        for row in stale_rows:
            row_age = round(age_hours(row.get("timestamp"), now_epoch=now_epoch), 3)
            stale_entry = {
                "timestamp": now_iso(),
                "task_hash": str(row.get("task_hash", "")).strip(),
                "task_preview": str(row.get("task_preview", ""))[:140],
                "task": str(row.get("task", ""))[:800],
                "attempt_mode": "drop_stale",
                "status": "ignored",
                "returncode": 0,
                "reason": "stale_age_exceeded",
                "dispatcher_reason": "stale_age_exceeded",
                "consensus_status": str(row.get("consensus_status", "")).strip().lower(),
                "age_hours": row_age,
                "stderr_tail": "",
            }
            new_result_rows.append(stale_entry)
            payload["results"].append(stale_entry)
            counts["ignored"] += 1
        payload["dropped_stale"] = len(stale_rows)

    for row in targets:
        task_hash = str(row.get("task_hash", "")).strip()
        row_age = round(age_hours(row.get("timestamp"), now_epoch=now_epoch), 3)
        returncode, dispatch_payload, stderr_tail = replay_task(
            row,
            mode=args.mode,
            allow_degraded=bool(args.allow_degraded),
            auto_lite_fallback=bool(args.auto_lite_fallback),
            council_retries=max(1, int(args.council_retries)),
        )
        status = classify_status(returncode, dispatch_payload)
        bucket = "blocked" if status in {"blocked", "blocked_lite"} else status
        if bucket not in counts:
            bucket = "error"
        counts[bucket] += 1

        dispatcher = dispatch_payload.get("dispatcher") if isinstance(dispatch_payload, dict) else {}
        consensus = dispatch_payload.get("consensus") if isinstance(dispatch_payload, dict) else {}
        result_entry = {
            "timestamp": now_iso(),
            "task_hash": task_hash,
            "task_preview": str(row.get("task_preview", ""))[:140],
            "task": str(row.get("task", ""))[:800],
            "attempt_mode": args.mode,
            "status": status,
            "returncode": int(returncode),
            "reason": str(row.get("reason", "")).strip().lower(),
            "age_hours": row_age,
            "dispatcher_reason": str(dispatcher.get("reason", "")).strip().lower()
            if isinstance(dispatcher, dict)
            else "",
            "consensus_status": str(consensus.get("status", "")).strip().lower()
            if isinstance(consensus, dict)
            else "",
            "stderr_tail": stderr_tail,
        }
        new_result_rows.append(result_entry)
        payload["results"].append(result_entry)

    payload["summary"] = {
        **counts,
        "stale_total": len(stale_rows),
        "dropped_stale": int(payload.get("dropped_stale", 0)),
    }

    removed = 0
    kept = len(pending_rows)
    with file_lock(lock_path, lock_timeout):
        latest_pending_rows = load_jsonl(pending_log)
        latest_result_rows = load_jsonl(result_log)
        append_jsonl_rows(result_log, new_result_rows)
        merged_result_rows = latest_result_rows + new_result_rows
        if args.compact_pending:
            compacted_rows, removed = compact_pending_rows(latest_pending_rows, merged_result_rows)
            kept = len(compacted_rows)
            if removed > 0:
                overwrite_jsonl(pending_log, compacted_rows)

    if args.compact_pending:
        payload["compaction"] = {"removed": int(removed), "kept": int(kept)}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(
            "resolved={resolved} blocked={blocked} ignored={ignored} error={error} "
            "selected={selected} open_total={open_total}".format(
                resolved=counts["resolved"],
                blocked=counts["blocked"],
                ignored=counts["ignored"],
                error=counts["error"],
                selected=payload["selected"],
                open_total=payload["open_total"],
            )
        )

    if counts["blocked"] > 0 or counts["error"] > 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
