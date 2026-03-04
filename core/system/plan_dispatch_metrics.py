#!/usr/bin/env python3
"""
plan_dispatch_metrics.py

JSONL metrics logger and summarizer for plan_dispatch runtime decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_PATH = Path(
    os.getenv(
        "PLAN_DISPATCH_METRICS_LOG",
        str(PROJECT_ROOT / "knowledge" / "system" / "plan_dispatch_metrics.jsonl"),
    )
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def append_metric(
    *,
    log_path: Path,
    task: str,
    mode: str,
    phase: str,
    reason: str,
    executed: bool,
    complexity: str = "unknown",
    score: int = 0,
    fallback: bool = False,
) -> Dict[str, Any]:
    task = (task or "").strip()
    task_hash = hashlib.sha1(task.encode("utf-8")).hexdigest()[:12] if task else ""
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "task_hash": task_hash,
        "task_preview": task[:140],
        "mode": str(mode or "").strip().lower() or "auto",
        "phase": str(phase or "").strip().lower() or "unknown",
        "reason": str(reason or "").strip().lower() or "unknown",
        "executed": bool(executed),
        "complexity": str(complexity or "").strip().lower() or "unknown",
        "score": int(score),
        "fallback": bool(fallback),
    }

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _load_entries(log_path: Path) -> List[Dict[str, Any]]:
    if not log_path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for raw in log_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            entries.append(obj)
    return entries


def summarize_metrics(*, log_path: Path, window: int = 200) -> Dict[str, Any]:
    entries = _load_entries(log_path)
    if window > 0:
        entries = entries[-window:]

    phase_counts = Counter()
    reason_counts = Counter()
    complexity_counts = Counter()
    mode_counts = Counter()
    executed_count = 0
    fallback_count = 0
    score_values: List[int] = []

    for entry in entries:
        phase_counts[str(entry.get("phase", "unknown"))] += 1
        reason_counts[str(entry.get("reason", "unknown"))] += 1
        complexity_counts[str(entry.get("complexity", "unknown"))] += 1
        mode_counts[str(entry.get("mode", "unknown"))] += 1

        if _to_bool(entry.get("executed")):
            executed_count += 1
        if _to_bool(entry.get("fallback")):
            fallback_count += 1

        try:
            score_values.append(int(entry.get("score", 0)))
        except Exception:
            score_values.append(0)

    total = len(entries)
    avg_score = round(sum(score_values) / total, 3) if total else 0.0
    executed_rate = round(executed_count / total, 3) if total else 0.0
    fallback_rate = round(fallback_count / total, 3) if total else 0.0

    return {
        "log_path": str(log_path),
        "window": window,
        "total": total,
        "executed_count": executed_count,
        "executed_rate": executed_rate,
        "fallback_count": fallback_count,
        "fallback_rate": fallback_rate,
        "avg_score": avg_score,
        "phase_counts": dict(phase_counts),
        "reason_counts": dict(reason_counts),
        "complexity_counts": dict(complexity_counts),
        "mode_counts": dict(mode_counts),
    }


def _print_human(summary: Dict[str, Any]) -> None:
    print("=== plan_dispatch metrics ===")
    print(f"log: {summary.get('log_path')}")
    print(f"window: {summary.get('window')} entries={summary.get('total')}")
    print(
        f"executed: {summary.get('executed_count')} "
        f"({summary.get('executed_rate')})"
    )
    print(
        f"fallback: {summary.get('fallback_count')} "
        f"({summary.get('fallback_rate')})"
    )
    print(f"avg_score: {summary.get('avg_score')}")
    print(f"phase_counts: {summary.get('phase_counts')}")
    print(f"reason_counts: {summary.get('reason_counts')}")
    print(f"complexity_counts: {summary.get('complexity_counts')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="plan_dispatch metrics logger/summary")
    parser.add_argument("--log", default=str(DEFAULT_LOG_PATH), help="JSONL log path")
    parser.add_argument("--append", action="store_true", help="append one metric event")
    parser.add_argument("--summary", action="store_true", help="print metrics summary")
    parser.add_argument("--window", type=int, default=200, help="summary window size")
    parser.add_argument("--json", action="store_true", help="print JSON output")

    parser.add_argument("--task", help="task text")
    parser.add_argument("--mode", default="auto", help="auto|manual")
    parser.add_argument("--phase", help="skip|smoke|execute|blocked|error")
    parser.add_argument("--reason", help="reason text")
    parser.add_argument("--executed", default="false", help="true|false")
    parser.add_argument("--complexity", default="unknown", help="complexity label")
    parser.add_argument("--score", default="0", help="numeric score")
    parser.add_argument("--fallback", default="false", help="true|false")
    args = parser.parse_args()

    if args.append == args.summary:
        print("ERROR choose exactly one: --append or --summary")
        return 1

    log_path = Path(args.log)

    if args.append:
        missing = [k for k in ("task", "phase", "reason") if not getattr(args, k)]
        if missing:
            print(f"ERROR missing required args for --append: {', '.join(missing)}")
            return 1

        try:
            score = int(str(args.score).strip())
        except Exception:
            score = 0

        payload = append_metric(
            log_path=log_path,
            task=args.task or "",
            mode=args.mode,
            phase=args.phase or "unknown",
            reason=args.reason or "unknown",
            executed=_to_bool(args.executed),
            complexity=args.complexity,
            score=score,
            fallback=_to_bool(args.fallback),
        )
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print("OK")
        return 0

    summary = summarize_metrics(log_path=log_path, window=args.window)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        _print_human(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
