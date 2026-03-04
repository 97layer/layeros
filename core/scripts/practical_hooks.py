#!/usr/bin/env python3
"""
Practical automation hooks for day-to-day agent work.

Implements:
1) start template (goal/files/checks/stop conditions)
2) file hash seal/check (sha1 drift detection)
3) mobile check gate (390/768/1440 via live_ui_monitor)
4) permission prompt budget bump/check
5) standardized completion report output
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = ROOT / "knowledge" / "system" / "practical_hooks_state.json"
DEFAULT_MOBILE_WIDTHS = "390,768,1440"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_repeat_csv(values: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    if not values:
        return out
    for raw in values:
        for token in str(raw).split(","):
            item = token.strip()
            if item:
                out.append(item)
    # dedupe while preserving order
    seen = set()
    uniq: List[str] = []
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        uniq.append(item)
    return uniq


def abs_path(path_str: str) -> Path:
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def rel_for_display(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def sha1_of_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"tasks": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"tasks": {}}
        if "tasks" not in data or not isinstance(data["tasks"], dict):
            data["tasks"] = {}
        return data
    except Exception:
        return {"tasks": {}}


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def get_task(state: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    tasks = state.setdefault("tasks", {})
    if task_id not in tasks:
        raise KeyError(f"task not found: {task_id}")
    task = tasks[task_id]
    if not isinstance(task, dict):
        raise KeyError(f"invalid task record: {task_id}")
    return task


def compute_hash_seal(files: List[str]) -> Dict[str, Optional[str]]:
    seal: Dict[str, Optional[str]] = {}
    for item in files:
        p = abs_path(item)
        seal[str(p)] = sha1_of_file(p)
    return seal


def cmd_start(args: argparse.Namespace) -> int:
    state_path = abs_path(args.state)
    state = load_state(state_path)

    task_id = args.task_id or datetime.now().strftime("task_%Y%m%d_%H%M%S")
    files = parse_repeat_csv(args.files)
    checks = parse_repeat_csv(args.checks)
    stop = args.stop or "hash drift detected | validation failed | permission budget exceeded"
    max_prompts = int(args.max_permission_prompts)

    if task_id in state.get("tasks", {}):
        print(f"ERROR task already exists: {task_id}", file=sys.stderr)
        return 2

    seal = compute_hash_seal(files)
    state["tasks"][task_id] = {
        "goal": args.goal,
        "files": files,
        "checks": checks,
        "stop_conditions": stop,
        "hash_seal": seal,
        "permission_requests": 0,
        "max_permission_prompts": max_prompts,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    save_state(state_path, state)

    files_line = ", ".join(files) if files else "(none)"
    checks_line = ", ".join(checks) if checks else "(none)"
    print(f"목표: {args.goal}")
    print(f"수정파일: {files_line}")
    print(f"검증명령: {checks_line}")
    print(f"중단조건: {stop}")
    print(f"TASK_ID={task_id}")
    return 0


def cmd_hash_seal(args: argparse.Namespace) -> int:
    state_path = abs_path(args.state)
    state = load_state(state_path)
    task = get_task(state, args.task_id)

    files = parse_repeat_csv(args.files) or list(task.get("files", []))
    if not files:
        print("ERROR no files to seal", file=sys.stderr)
        return 2

    task["files"] = files
    task["hash_seal"] = compute_hash_seal(files)
    task["updated_at"] = now_iso()
    save_state(state_path, state)

    print(f"HASH_SEAL_UPDATED={args.task_id}")
    for item, digest in task["hash_seal"].items():
        shown = rel_for_display(Path(item))
        print(f"  {shown} -> {digest or 'MISSING'}")
    return 0


def cmd_hash_check(args: argparse.Namespace) -> int:
    state_path = abs_path(args.state)
    state = load_state(state_path)
    task = get_task(state, args.task_id)

    seal = task.get("hash_seal", {})
    if not isinstance(seal, dict) or not seal:
        print("ERROR no hash seal found; run hash-seal first", file=sys.stderr)
        return 2

    drift: List[str] = []
    for file_abs, old_digest in seal.items():
        p = Path(file_abs)
        new_digest = sha1_of_file(p)
        if new_digest != old_digest:
            drift.append(
                f"{rel_for_display(p)} old={old_digest or 'MISSING'} new={new_digest or 'MISSING'}"
            )

    if drift:
        print(f"HASH_DRIFT={args.task_id}")
        for row in drift:
            print(f"  {row}")
        return 3

    print(f"HASH_OK={args.task_id}")
    return 0


def parse_widths(raw: str) -> List[int]:
    vals: List[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        vals.append(int(token))
    if not vals:
        raise ValueError("no widths provided")
    return vals


def cmd_mobile_check(args: argparse.Namespace) -> int:
    widths = parse_widths(args.widths)
    widths_csv = ",".join(str(x) for x in widths)

    monitor_script = ROOT / "core" / "scripts" / "live_ui_monitor.py"
    cmd = [
        sys.executable,
        str(monitor_script),
        "--once",
        "--session",
        args.session,
        "--urls",
        args.urls,
        "--widths",
        widths_csv,
        "--height",
        str(args.height),
    ]
    if args.headed:
        cmd.append("--headed")

    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    print(output.rstrip())

    if proc.returncode != 0:
        print("MOBILE_CHECK=FAIL command_error", file=sys.stderr)
        return proc.returncode

    fail_lines = [ln for ln in output.splitlines() if ln.startswith("[FAIL]")]
    for width in widths:
        if not re.search(rf"\bvw={width}\b", output):
            print(f"MOBILE_CHECK=FAIL missing_viewport:{width}", file=sys.stderr)
            return 3
    if fail_lines:
        print("MOBILE_CHECK=FAIL ui_contract", file=sys.stderr)
        return 4

    print("MOBILE_CHECK=PASS")
    return 0


def cmd_permission_bump(args: argparse.Namespace) -> int:
    state_path = abs_path(args.state)
    state = load_state(state_path)
    task = get_task(state, args.task_id)

    count = int(task.get("permission_requests", 0)) + 1
    limit = int(task.get("max_permission_prompts", 1))
    task["permission_requests"] = count
    task["updated_at"] = now_iso()
    save_state(state_path, state)

    print(f"PERMISSION_REQUESTS={count}/{limit} task={args.task_id}")
    if count > limit:
        print("PERMISSION_BUDGET_EXCEEDED", file=sys.stderr)
        return 3
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    changed = ", ".join(parse_repeat_csv(args.files)) if args.files else "(none)"
    checks = ", ".join(parse_repeat_csv(args.checks)) if args.checks else "(none)"
    risks = args.risks.strip() if args.risks else "(none)"
    print(f"변경파일: {changed}")
    print(f"실행검증: {checks}")
    print(f"실패위험: {risks}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Practical automation hooks")
    p.add_argument(
        "--state",
        default=str(DEFAULT_STATE),
        help="state json path (default: knowledge/system/practical_hooks_state.json)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start", help="create task and print 4-line start template")
    start.add_argument("--task-id", default="")
    start.add_argument("--goal", required=True)
    start.add_argument("--files", action="append", default=[])
    start.add_argument("--checks", action="append", default=[])
    start.add_argument("--stop", default="")
    start.add_argument("--max-permission-prompts", type=int, default=1)
    start.set_defaults(func=cmd_start)

    seal = sub.add_parser("hash-seal", help="seal current hashes for task files")
    seal.add_argument("--task-id", required=True)
    seal.add_argument("--files", action="append", default=[])
    seal.set_defaults(func=cmd_hash_seal)

    check = sub.add_parser("hash-check", help="check current hashes against seal")
    check.add_argument("--task-id", required=True)
    check.set_defaults(func=cmd_hash_check)

    mobile = sub.add_parser("mobile-check", help="run 390/768/1440 viewport check")
    mobile.add_argument("--urls", required=True, help="comma-separated URLs")
    mobile.add_argument("--widths", default=DEFAULT_MOBILE_WIDTHS)
    mobile.add_argument("--height", type=int, default=900)
    mobile.add_argument("--session", default="practical-mobile")
    mobile.add_argument("--headed", action="store_true")
    mobile.set_defaults(func=cmd_mobile_check)

    perm = sub.add_parser("permission-bump", help="increment permission request counter")
    perm.add_argument("--task-id", required=True)
    perm.set_defaults(func=cmd_permission_bump)

    report = sub.add_parser("report", help="print standardized 3-line completion report")
    report.add_argument("--files", action="append", default=[])
    report.add_argument("--checks", action="append", default=[])
    report.add_argument("--risks", default="")
    report.set_defaults(func=cmd_report)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except KeyError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
