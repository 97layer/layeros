#!/usr/bin/env python3
"""
harness_doctor.py

LAYER OS 풀스택 하네스 준비도 점검:
- 필수 스크립트/파일 존재
- Python 모듈 의존성
- MCP 등록 상태 (codex mcp list)
- 선택: 핵심 테스트 실행
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_FILE = PROJECT_ROOT / "knowledge" / "system" / "harness_doctor_reports.jsonl"

REQUIRED_FILES = (
    "core/scripts/start_harness_fullstack.sh",
    "core/scripts/harness_status.sh",
    "core/scripts/run_web_rebuild_prep.sh",
    "core/scripts/web_rebuild_prep.py",
    "core/scripts/plan_dispatch.sh",
    "core/system/plan_council.py",
    ".claude/hooks/plan-council.sh",
    ".claude/rules/plan-council.md",
    ".claude/rules/model-role-routing.md",
    ".claude/commands/plan.md",
    ".claude/commands/plan-council.md",
    "core/system/pipeline_orchestrator.py",
    "core/agents/sa_agent.py",
    "core/agents/ad_agent.py",
    "core/agents/ce_agent.py",
    "core/agents/cd_agent.py",
    "core/backend/main.py",
    "core/backend/app.py",
    "core/backend/photo_upload.py",
    "core/backend/ecommerce/main.py",
)

REQUIRED_MODULES = (
    "requests",
    "jinja2",
)

OPTIONAL_MODULES = (
    "markdown",
    "feedparser",
)

REQUIRED_MCP = ("context7", "sequential-thinking", "notebooklm")


@dataclass
class CheckResult:
    name: str
    status: str  # pass, warn, fail
    detail: str


def run_command(cmd: List[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def check_files() -> CheckResult:
    missing = [rel for rel in REQUIRED_FILES if not (PROJECT_ROOT / rel).exists()]
    if missing:
        return CheckResult("files", "fail", f"missing: {', '.join(missing)}")
    return CheckResult("files", "pass", "all required files present")


def check_modules() -> CheckResult:
    missing = []
    optional_missing = []
    for mod in REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)

    for mod in OPTIONAL_MODULES:
        try:
            importlib.import_module(mod)
        except ImportError:
            optional_missing.append(mod)

    if missing:
        return CheckResult("python-modules", "fail", f"missing: {', '.join(missing)}")

    if optional_missing:
        return CheckResult("python-modules", "warn", f"optional missing: {', '.join(optional_missing)}")

    return CheckResult("python-modules", "pass", "all required modules importable")


def check_mcp() -> CheckResult:
    code, out, err = run_command(["codex", "mcp", "list"])
    if code != 0:
        short = (err or out or "codex mcp list failed")[:180]
        return CheckResult("mcp", "warn", f"check skipped: {short}")

    listed = out.lower()
    missing = [m for m in REQUIRED_MCP if m not in listed]
    if missing:
        return CheckResult("mcp", "warn", f"missing in codex config: {', '.join(missing)}")
    return CheckResult("mcp", "pass", "required mcp registered")


def check_env() -> CheckResult:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return CheckResult("env", "warn", ".env not found")

    text = env_file.read_text(encoding="utf-8", errors="ignore")
    if "GOOGLE_API_KEY=" in text or "GEMINI_API_KEY=" in text:
        if "ANTHROPIC_API_KEY=" in text:
            return CheckResult("env", "pass", "Gemini + Anthropic key variables present in .env")
        return CheckResult("env", "warn", "Gemini key present, ANTHROPIC_API_KEY missing")
    return CheckResult("env", "warn", "GOOGLE_API_KEY/GEMINI_API_KEY not found in .env")


def check_work_lock() -> CheckResult:
    primary_path = PROJECT_ROOT / "knowledge" / "system" / "web_work_lock.json"
    legacy_path = PROJECT_ROOT / "knowledge" / "system" / "work_lock.json"

    if not primary_path.exists():
        return CheckResult("work-lock", "fail", "web_work_lock.json missing")

    try:
        primary_payload = json.loads(primary_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return CheckResult("work-lock", "fail", f"invalid web_work_lock.json ({exc})")

    locked = primary_payload.get("locked")
    if locked is True:
        return CheckResult("work-lock", "warn", "web_work_lock.json is locked=true")

    if legacy_path.exists():
        try:
            json.loads(legacy_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return CheckResult("work-lock", "warn", f"legacy work_lock.json invalid ({exc})")
        return CheckResult("work-lock", "pass", "web_work_lock + legacy work_lock present")

    return CheckResult("work-lock", "pass", "web_work_lock.json present (legacy work_lock omitted)")


def check_plan_council() -> CheckResult:
    code, out, err = run_command(
        ["python3", "core/system/plan_council.py", "--self-check", "--require-both"]
    )
    if code != 0:
        text = (out or err or "plan council self-check failed").splitlines()
        short = (text[-1] if text else "plan council self-check failed")[:180]
        return CheckResult("plan-council", "fail", short)
    return CheckResult("plan-council", "pass", "claude+gemini planning council ready")


def check_gateway_contract() -> CheckResult:
    gateway_path = PROJECT_ROOT / "core/backend/main.py"
    if not gateway_path.exists():
        return CheckResult("gateway-contract", "fail", "core/backend/main.py missing")

    text = gateway_path.read_text(encoding="utf-8", errors="ignore")
    required_tokens = (
        '"/healthz"',
        '"/harness/status"',
        '"/queue/pending"',
        '"/queue/task"',
        '"/cms"',
        '"/upload"',
        '"/commerce"',
    )
    missing = [token for token in required_tokens if token not in text]
    if missing:
        return CheckResult("gateway-contract", "fail", f"missing: {', '.join(missing)}")
    return CheckResult("gateway-contract", "pass", "gateway mounts + control APIs detected")


def check_plan_dispatch() -> CheckResult:
    auto_cmd = ["bash", "core/scripts/plan_dispatch.sh", "ok", "--auto"]
    manual_cmd = ["bash", "core/scripts/plan_dispatch.sh", "하네스 구조 리팩토링 계획 점검", "--manual"]

    for label, cmd in (("auto", auto_cmd), ("manual", manual_cmd)):
        code, out, err = run_command(cmd)
        if code != 0:
            short = (err or out or f"plan dispatch {label} failed").splitlines()
            msg = (short[-1] if short else f"plan dispatch {label} failed")[:180]
            return CheckResult("plan-dispatch", "fail", f"{label}: {msg}")
        try:
            payload = json.loads(out)
        except Exception as exc:  # noqa: BLE001
            return CheckResult("plan-dispatch", "fail", f"{label}: invalid json ({exc})")

        dispatcher = payload.get("dispatcher")
        consensus = payload.get("consensus")
        if not isinstance(dispatcher, dict) or not isinstance(consensus, dict):
            return CheckResult("plan-dispatch", "fail", f"{label}: missing dispatcher/consensus")

        if label == "manual" and dispatcher.get("executed") is not True:
            return CheckResult("plan-dispatch", "fail", "manual: dispatcher did not execute council")

    return CheckResult("plan-dispatch", "pass", "auto skip + manual execution paths ready")


def check_model_role_routing() -> CheckResult:
    contract_path = PROJECT_ROOT / "knowledge/system/agent_runtime_contract.json"
    if not contract_path.exists():
        return CheckResult("role-routing", "fail", "agent_runtime_contract.json missing")
    try:
        data = json.loads(contract_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return CheckResult("role-routing", "fail", f"contract parse error: {exc}")

    role = data.get("model_role_contract", {})
    if not isinstance(role, dict):
        return CheckResult("role-routing", "fail", "model_role_contract missing")

    planner = str(role.get("planner", "")).lower()
    coder = str(role.get("coder", "")).lower()
    verifier = str(role.get("verifier", "")).lower()
    strict = role.get("forbid_role_inversion") is True

    if planner == "claude" and coder == "codex" and verifier == "gemini" and strict:
        return CheckResult("role-routing", "pass", "Claude=Plan / Codex=Code / Gemini=Verify")

    detail = (
        f"planner={planner or '?'} coder={coder or '?'} "
        f"verifier={verifier or '?'} strict={strict}"
    )
    return CheckResult("role-routing", "fail", detail)


def check_tests(run_tests: bool) -> CheckResult:
    if not run_tests:
        return CheckResult("tests", "warn", "skipped (--run-tests not set)")

    env = dict(**{"LAYER_DISABLE_FILESYSTEM_GUARD": "1"}, **dict())
    code, out, err = subprocess_run_with_env(
        ["pytest", "-q", "core/tests/test_queue_manager.py", "core/tests/test_handoff.py"],
        extra_env=env,
    )
    if code != 0:
        text = (out or err or "tests failed").splitlines()[-1][:180]
        return CheckResult("tests", "fail", text)
    summary = (out.splitlines()[-1] if out else "tests passed")[:180]
    return CheckResult("tests", "pass", summary)


def subprocess_run_with_env(cmd: List[str], extra_env: dict) -> Tuple[int, str, str]:
    env = os.environ.copy()
    env.update(extra_env)
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def score(results: List[CheckResult]) -> int:
    points = 0
    for r in results:
        if r.status == "pass":
            points += 20
        elif r.status == "warn":
            points += 10
    return min(points, 100)


def overall_status(results: List[CheckResult], readiness_score: int) -> str:
    if any(r.status == "fail" for r in results):
        return "fail"
    if readiness_score < 80:
        return "warn"
    return "pass"


def print_report(results: List[CheckResult], readiness_score: int, overall: str) -> None:
    icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
    print("\n=== Harness Doctor ===")
    for r in results:
        print(f"{icon[r.status]} {r.name:<15} [{r.status}] {r.detail}")
    print(f"Readiness Score: {readiness_score}/100")
    print(f"Overall: {overall.upper()}")
    print(f"Report: {REPORT_FILE}")


def append_report(results: List[CheckResult], readiness_score: int, overall: str) -> None:
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "score": readiness_score,
        "overall": overall,
        "checks": [asdict(r) for r in results],
    }
    with open(REPORT_FILE, "a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="LAYER OS Fullstack Harness readiness doctor")
    parser.add_argument("--run-tests", action="store_true", help="run core queue/handoff tests")
    args = parser.parse_args()

    results = [
        check_files(),
        check_modules(),
        check_mcp(),
        check_env(),
        check_gateway_contract(),
        check_plan_council(),
        check_plan_dispatch(),
        check_model_role_routing(),
        check_work_lock(),
        check_tests(args.run_tests),
    ]

    readiness_score = score(results)
    overall = overall_status(results, readiness_score)
    append_report(results, readiness_score, overall)
    print_report(results, readiness_score, overall)
    return 0 if overall == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
