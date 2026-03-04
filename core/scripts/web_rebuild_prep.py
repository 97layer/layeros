#!/usr/bin/env python3
"""
web_rebuild_prep.py

리빌드 전 필수 게이트:
1) MCP/스킬/필수 파일 준비 상태 점검
2) web consistency lock 획득
3) 수치 기반 시각 검증
4) 빌드 실행
5) localhost:9700 스모크 검증
6) 결과 리포트 저장
"""

from __future__ import annotations

import argparse
import importlib
import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.error import URLError, HTTPError
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_FILE = PROJECT_ROOT / "knowledge" / "system" / "web_rebuild_reports.jsonl"
DEFAULT_SMOKE_PATHS = ["/", "/about/", "/practice/", "/archive/", "/assets/css/style.css"]
REQUIRED_MCP = ("context7", "sequential-thinking", "notebooklm")
REQUIRED_PY_MODULES = ("jinja2",)
OPTIONAL_PY_MODULES = ("markdown", "feedparser")
REQUIRED_SKILLS = (
    "core/skills/signal_capture/SKILL.md",
    "core/skills/data_curation/SKILL.md",
    "core/skills/deploy/SKILL.md",
    "core/skills/infrastructure_sentinel/SKILL.md",
    "core/skills/intelligence_backup/SKILL.md",
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.system.visual_validator import VisualValidator  # noqa: E402
from core.system.web_consistency_lock import (  # noqa: E402
    acquire_lock,
    check_lock,
    release_lock,
    validate_changes,
)


@dataclass
class StepResult:
    name: str
    status: str  # pass, warn, fail
    detail: str
    elapsed_ms: int

    @property
    def ok(self) -> bool:
        return self.status in ("pass", "warn")


class RebuildPrepError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def run_command(cmd: List[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def check_tooling() -> StepResult:
    start = time.perf_counter()
    missing = []
    missing_modules = []
    optional_missing = []
    for rel in REQUIRED_SKILLS:
        if not (PROJECT_ROOT / rel).exists():
            missing.append(rel)

    for module_name in REQUIRED_PY_MODULES:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing_modules.append(module_name)

    for module_name in OPTIONAL_PY_MODULES:
        try:
            importlib.import_module(module_name)
        except ImportError:
            optional_missing.append(module_name)

    details = []
    if missing or missing_modules:
        status = "fail"
        if missing:
            details.append(f"missing skills: {', '.join(missing)}")
        if missing_modules:
            details.append(f"missing python modules: {', '.join(missing_modules)}")
    else:
        status = "pass"
        details.append("core skills files and python deps present")
        if optional_missing:
            status = "warn"
            details.append(f"optional modules missing: {', '.join(optional_missing)}")

    code, out, err = run_command(["codex", "mcp", "list"])
    if code != 0:
        status = "warn" if status == "pass" else status
        short_err = (err or out or "codex mcp list failed")[:160]
        details.append(f"mcp check skipped: {short_err}")
    else:
        listed = out.lower()
        missing_mcp = [name for name in REQUIRED_MCP if name not in listed]
        if missing_mcp:
            status = "warn" if status == "pass" else status
            details.append(f"missing mcp in codex config: {', '.join(missing_mcp)}")
        else:
            details.append("required mcp registered")

    elapsed = int((time.perf_counter() - start) * 1000)
    return StepResult("tooling", status, " | ".join(details), elapsed)


def check_visual(fail_on_warning: bool) -> StepResult:
    start = time.perf_counter()
    validator = VisualValidator(project_root=str(PROJECT_ROOT))
    issues = validator.validate_all()
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    if errors:
        status = "fail"
    elif warnings and fail_on_warning:
        status = "fail"
    elif warnings:
        status = "warn"
    else:
        status = "pass"

    detail = f"errors={len(errors)}, warnings={len(warnings)}"
    if errors:
        first = errors[0]
        detail += f" | first_error={first.file}:{first.line} {first.message}"
    elif warnings:
        first = warnings[0]
        detail += f" | first_warning={first.file}:{first.line} {first.message}"

    elapsed = int((time.perf_counter() - start) * 1000)
    return StepResult("visual-validator", status, detail, elapsed)


def run_build(dry_run: bool, full_build: bool) -> StepResult:
    start = time.perf_counter()
    cmd = [sys.executable, "core/scripts/build.py"]
    if not full_build:
        cmd.extend(["--components", "--bust"])
    if dry_run:
        cmd.append("--dry-run")
    code, out, err = run_command(cmd)
    elapsed = int((time.perf_counter() - start) * 1000)

    if code != 0:
        detail = (err or out or "build failed")[:240]
        return StepResult("build", "fail", detail, elapsed)

    last_line = (out.splitlines()[-1] if out else "build complete")
    return StepResult("build", "pass", last_line[:240], elapsed)


def request(url: str, timeout: float = 3.0) -> Tuple[bool, str]:
    try:
        with urlopen(url, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if 200 <= status < 400:
                return True, f"{status}"
            return False, f"{status}"
    except HTTPError as exc:
        return False, f"http {exc.code}"
    except URLError as exc:
        return False, f"url {exc.reason}"
    except Exception as exc:  # pragma: no cover
        return False, str(exc)


def ensure_server(port: int, timeout_sec: float) -> Tuple[Optional[subprocess.Popen], bool]:
    if is_port_open("127.0.0.1", port):
        return None, False

    proc = subprocess.Popen(
        [sys.executable, "core/scripts/dev_server.py"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    started = time.time()
    while time.time() - started <= timeout_sec:
        if proc.poll() is not None:
            log = ""
            if proc.stdout is not None:
                log = (proc.stdout.read() or "").strip().replace("\n", " ")
            detail = f"dev_server.py exited ({proc.returncode})"
            if log:
                tail = log[-220:] if len(log) > 220 else log
                detail = f"{detail}: {tail}"
            raise RebuildPrepError(detail)

        if is_port_open("127.0.0.1", port):
            return proc, True
        time.sleep(0.1)

    proc.terminate()
    proc.wait(timeout=2)
    raise RebuildPrepError(f"localhost:{port} did not open within {timeout_sec}s")


def smoke_test(port: int, paths: List[str], timeout_sec: float) -> StepResult:
    start = time.perf_counter()
    server_proc: Optional[subprocess.Popen] = None
    server_started = False
    failures = []

    try:
        try:
            server_proc, server_started = ensure_server(port, timeout_sec)
        except RebuildPrepError as exc:
            elapsed = int((time.perf_counter() - start) * 1000)
            detail = str(exc)
            if "Operation not permitted" in detail or "PermissionError" in detail:
                return StepResult("smoke", "warn", f"skipped (sandbox restriction): {detail[:160]}", elapsed)
            return StepResult("smoke", "fail", detail, elapsed)

        base = f"http://127.0.0.1:{port}"
        for path in paths:
            ok, detail = request(base + path)
            if not ok:
                failures.append(f"{path} ({detail})")
    finally:
        if server_proc is not None and server_started:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                server_proc.kill()

    elapsed = int((time.perf_counter() - start) * 1000)
    if failures:
        return StepResult("smoke", "fail", f"failed: {', '.join(failures)}", elapsed)
    source = "existing server" if not server_started else "auto-started dev_server.py"
    return StepResult("smoke", "pass", f"{len(paths)} urls ok via {source}", elapsed)


def lock_step(agent: str, task: str) -> Tuple[StepResult, bool]:
    start = time.perf_counter()
    current = check_lock()

    if current.get("locked"):
        holder = current.get("agent", "unknown")
        if holder != agent:
            elapsed = int((time.perf_counter() - start) * 1000)
            return StepResult(
                "lock",
                "fail",
                f"lock held by {holder} ({current.get('task', 'unknown task')})",
                elapsed,
            ), False
        elapsed = int((time.perf_counter() - start) * 1000)
        return StepResult("lock", "warn", f"reusing existing lock for {agent}", elapsed), False

    ok = acquire_lock(agent, task)
    elapsed = int((time.perf_counter() - start) * 1000)
    if not ok:
        return StepResult("lock", "fail", "failed to acquire web lock", elapsed), False
    return StepResult("lock", "pass", f"acquired by {agent}", elapsed), True


def validate_lock_changes(agent: str) -> StepResult:
    start = time.perf_counter()
    ok = validate_changes(agent)
    elapsed = int((time.perf_counter() - start) * 1000)
    if not ok:
        return StepResult("lock-validate", "fail", "web consistency validation failed", elapsed)
    return StepResult("lock-validate", "pass", "consistency validation passed", elapsed)


def append_report(args: argparse.Namespace, steps: List[StepResult], overall: str) -> None:
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": now_iso(),
        "overall": overall,
        "agent": args.agent,
        "task": args.task,
        "options": {
            "build_dry_run": args.build_dry_run,
            "skip_lock": args.skip_lock,
            "skip_visual": args.skip_visual,
            "skip_build": args.skip_build,
            "full_build": args.full_build,
            "skip_smoke": args.skip_smoke,
            "fail_on_warning": args.fail_on_warning,
            "keep_lock": args.keep_lock,
        },
        "steps": [asdict(step) for step in steps],
    }
    with open(REPORT_FILE, "a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def print_summary(steps: List[StepResult], overall: str) -> None:
    print("\n=== Web Rebuild Prep Summary ===")
    for step in steps:
        icon = "✅" if step.status == "pass" else ("⚠️" if step.status == "warn" else "❌")
        print(f"{icon} {step.name:<16} [{step.status}] {step.detail} ({step.elapsed_ms}ms)")
    print(f"Overall: {overall.upper()}")
    print(f"Report: {REPORT_FILE}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="리빌드 전 E2E 프리플라이트")
    parser.add_argument("--agent", default="HUMAN", help="lock agent id (default: HUMAN)")
    parser.add_argument("--task", default="web rebuild prep", help="lock task description")
    parser.add_argument("--build-dry-run", action="store_true", help="build.py dry-run")
    parser.add_argument("--skip-lock", action="store_true", help="skip lock acquire/validate")
    parser.add_argument("--skip-visual", action="store_true", help="skip visual validator")
    parser.add_argument("--skip-build", action="store_true", help="skip build step")
    parser.add_argument("--full-build", action="store_true", help="run full build (includes archive)")
    parser.add_argument("--skip-smoke", action="store_true", help="skip localhost smoke test")
    parser.add_argument("--fail-on-warning", action="store_true", help="treat visual warnings as failure")
    parser.add_argument("--keep-lock", action="store_true", help="keep lock if this run acquired it")
    parser.add_argument("--port", type=int, default=9700, help="smoke test port (default: 9700)")
    parser.add_argument(
        "--server-timeout",
        type=float,
        default=8.0,
        help="seconds to wait when auto-starting dev server",
    )
    parser.add_argument(
        "--smoke-path",
        action="append",
        dest="smoke_paths",
        default=[],
        help="additional path for smoke test (repeatable)",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    steps: List[StepResult] = []
    acquired_by_run = False
    overall = "pass"

    try:
        step = check_tooling()
        steps.append(step)
        if not step.ok:
            raise RebuildPrepError(step.detail)

        if not args.skip_lock:
            step, acquired_by_run = lock_step(args.agent, args.task)
            steps.append(step)
            if not step.ok:
                raise RebuildPrepError(step.detail)

        if not args.skip_visual:
            step = check_visual(args.fail_on_warning)
            steps.append(step)
            if not step.ok:
                raise RebuildPrepError(step.detail)

        if not args.skip_build:
            step = run_build(args.build_dry_run, args.full_build)
            steps.append(step)
            if not step.ok:
                raise RebuildPrepError(step.detail)

        if not args.skip_smoke:
            unique_paths = list(dict.fromkeys(DEFAULT_SMOKE_PATHS + args.smoke_paths))
            step = smoke_test(args.port, unique_paths, args.server_timeout)
            steps.append(step)
            if not step.ok:
                raise RebuildPrepError(step.detail)

        if not args.skip_lock:
            step = validate_lock_changes(args.agent)
            steps.append(step)
            if not step.ok:
                raise RebuildPrepError(step.detail)

    except RebuildPrepError:
        overall = "fail"
    except KeyboardInterrupt:
        overall = "fail"
        steps.append(StepResult("interrupt", "fail", "interrupted by user", 0))
    finally:
        if acquired_by_run and not args.keep_lock:
            release_lock(args.agent)

    append_report(args, steps, overall)
    print_summary(steps, overall)
    return 0 if overall == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
