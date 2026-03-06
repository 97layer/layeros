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
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
REPORT_FILE = PROJECT_ROOT / "knowledge" / "system" / "harness_doctor_reports.jsonl"

REQUIRED_FILES = (
    "core/scripts/start_harness_fullstack.sh",
    "core/scripts/harness_status.sh",
    "core/scripts/run_web_rebuild_prep.sh",
    "core/scripts/web_rebuild_prep.py",
    "core/scripts/pipeline_resilience_smoke.py",
    "core/scripts/pipeline_resilience_runner.sh",
    "core/scripts/pipeline_resilience_install_cron.sh",
    "core/scripts/hooks/pre-commit",
    "core/scripts/hooks/pre-push",
    "core/scripts/hooks/post-commit",
    "core/scripts/hooks/trigger_autodeploy.sh",
    "core/scripts/hooks/install_git_hooks.sh",
    "core/scripts/plan_dispatch.sh",
    "core/scripts/plan_dispatch_daily_report.py",
    "core/scripts/plan_dispatch_pending_replay.py",
    "core/scripts/skill_tool_audit.py",
    "core/system/plan_council.py",
    "core/system/plan_dispatch_metrics.py",
    "core/system/plan_dispatch_replay.py",
    "core/system/progress_graph.py",
    ".claude/hooks/plan-council.sh",
    ".claude/hooks/progress-snapshot.sh",
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

try:
    from core.system.progress_graph import build_progress_payload
except Exception:  # noqa: BLE001
    build_progress_payload = None


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


def parse_json_output(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty output")
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
            if isinstance(payload, dict):
                return payload
        except Exception:
            continue
    raise ValueError("no json object found in output")


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


def check_asset_registry_integrity() -> CheckResult:
    registry_path = PROJECT_ROOT / "knowledge" / "system" / "asset_registry.json"
    if not registry_path.exists():
        return CheckResult("asset-registry", "warn", "asset_registry.json missing")

    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return CheckResult("asset-registry", "fail", f"invalid json ({exc})")

    assets = payload.get("assets")
    if not isinstance(assets, list):
        return CheckResult("asset-registry", "fail", "assets must be list")

    ast_ids = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        value = item.get("id")
        if isinstance(value, str) and value.startswith("AST-"):
            ast_ids.append(value)
    dup_ast = sorted({x for x in ast_ids if ast_ids.count(x) > 1})
    if dup_ast:
        return CheckResult(
            "asset-registry",
            "fail",
            f"duplicate AST ids: {', '.join(dup_ast[:5])}",
        )

    stats = payload.get("stats", {})
    if not isinstance(stats, dict):
        return CheckResult("asset-registry", "warn", "stats missing")
    total = stats.get("total")
    if isinstance(total, int) and total != len(assets):
        return CheckResult("asset-registry", "warn", f"stats.total={total} assets={len(assets)}")

    return CheckResult("asset-registry", "pass", f"assets={len(assets)} ast_ids={len(ast_ids)}")


def check_plan_council() -> CheckResult:
    code, out, err = run_command(
        ["python3", "core/system/plan_council.py", "--self-check", "--require-both"]
    )
    if code != 0:
        text = (out or err or "plan council self-check failed").splitlines()
        short = (text[-1] if text else "plan council self-check failed")[:180]
        return CheckResult("plan-council", "fail", short)
    return CheckResult("plan-council", "pass", "claude+gemini planning council ready")


def check_council_worker() -> CheckResult:
    """
    Enforce asynchronous council queue consumer availability.
    Required by default (COUNCIL_WORKER_REQUIRED=1).
    """
    required = str(os.getenv("COUNCIL_WORKER_REQUIRED", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
    timer_unit = os.getenv("COUNCIL_WORKER_TIMER_UNIT", "council-worker.timer")
    service_unit = os.getenv("COUNCIL_WORKER_SERVICE_UNIT", "council-worker.service")
    process_pattern = os.getenv("COUNCIL_WORKER_PROCESS_PATTERN", "core/daemons/council_worker.py")
    pending_dirs = {
        "council": PROJECT_ROOT / ".infra" / "queue" / "council" / "pending",
        "council_room": PROJECT_ROOT / ".infra" / "queue" / "council_room" / "pending",
    }
    pending_counts = {
        name: (len(list(path.glob("*.json"))) if path.exists() else 0) for name, path in pending_dirs.items()
    }
    pending_count = sum(pending_counts.values())

    active_signals: List[str] = []
    if shutil.which("systemctl"):
        for unit in (timer_unit, service_unit):
            code, out, _ = run_command(["systemctl", "is-active", unit])
            if code == 0 and out.strip() == "active":
                active_signals.append(f"systemd:{unit}")

    # macOS 등 로컬에 systemctl 없는 경우 deploy.sh --status로 VM 원격 확인
    if not active_signals and not shutil.which("systemctl"):
        deploy_sh = PROJECT_ROOT / "core/scripts/deploy/deploy.sh"
        if deploy_sh.exists():
            code, out, _ = run_command(["bash", str(deploy_sh), "--status"])
            if code == 0:
                for line in out.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[0] == "council-worker" and parts[1].startswith("active"):
                        active_signals.append("vm:deploy-status")
                        break

    if shutil.which("pgrep"):
        code, out, _ = run_command(["pgrep", "-f", process_pattern])
        if code == 0 and out.strip():
            active_signals.append("process:pgrep")

    if active_signals:
        return CheckResult(
            "council-worker",
            "pass",
            (
                f"active via {', '.join(active_signals)} pending={pending_count} "
                f"council={pending_counts['council']} council_room={pending_counts['council_room']}"
            ),
        )

    detail = (
        f"inactive pending={pending_count} council={pending_counts['council']} "
        f"council_room={pending_counts['council_room']} timer={timer_unit} service={service_unit} "
        f"pattern={process_pattern}"
    )
    if required:
        return CheckResult("council-worker", "fail", detail)
    return CheckResult("council-worker", "warn", detail)


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
    simple_auto_task = "ok"
    manual_task = (
        "다중 파일 웹 개편 작업: website/archive/index.html, website/practice/index.html, "
        "website/lab/index.html의 레이아웃 간격/타이포 일관성만 조정하고 "
        "about 텍스트 및 백엔드/인프라는 변경하지 않는다. "
        "변경 후 visual_validator와 build_components로 검증한다."
    )
    nontrivial_auto_task = "스킬 및 기본 툴 체계를 분석하고 업그레이드 항목을 구현한다"
    auto_cmd = ["bash", "core/scripts/plan_dispatch.sh", simple_auto_task, "--auto", "--smoke"]
    auto_nontrivial_cmd = [
        "bash",
        "core/scripts/plan_dispatch.sh",
        nontrivial_auto_task,
        "--auto",
        "--smoke",
    ]
    manual_cmd = ["bash", "core/scripts/plan_dispatch.sh", manual_task, "--manual", "--smoke"]

    for label, cmd in (
        ("auto-simple", auto_cmd),
        ("auto-nontrivial", auto_nontrivial_cmd),
        ("manual", manual_cmd),
    ):
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

        if label == "auto-simple":
            if dispatcher.get("executed") is not False:
                return CheckResult("plan-dispatch", "fail", "auto-simple: expected skip path")
            if dispatcher.get("reason") != "simple_task":
                return CheckResult("plan-dispatch", "fail", "auto-simple: expected reason=simple_task")

        if label == "auto-nontrivial":
            if dispatcher.get("executed") is not True:
                return CheckResult("plan-dispatch", "fail", "auto-nontrivial: expected execute path")
            if dispatcher.get("complexity") not in {"medium", "high"}:
                return CheckResult("plan-dispatch", "fail", "auto-nontrivial: complexity must be medium/high")

        if label == "manual" and dispatcher.get("executed") is not True:
            return CheckResult("plan-dispatch", "fail", "manual: dispatcher did not execute council")

    return CheckResult("plan-dispatch", "pass", "auto simple/nontrivial + manual paths ready")


def check_plan_dispatch_observability() -> CheckResult:
    code, out, err = run_command(
        ["python3", "core/system/plan_dispatch_metrics.py", "--summary", "--window", "200", "--json"]
    )
    if code != 0:
        short = (err or out or "plan_dispatch_metrics summary failed").splitlines()
        msg = (short[-1] if short else "plan_dispatch_metrics summary failed")[:180]
        return CheckResult("plan-observe", "warn", msg)

    try:
        payload = parse_json_output(out)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("plan-observe", "warn", f"invalid json ({exc})")

    total = int(payload.get("total", 0))
    fallback_rate = float(payload.get("fallback_rate", 0.0))
    threshold = float(os.getenv("PLAN_DISPATCH_FALLBACK_WARN_RATE", "0.30"))
    min_samples = int(os.getenv("PLAN_DISPATCH_FALLBACK_MIN_SAMPLES", "20"))

    if total < min_samples:
        return CheckResult(
            "plan-observe",
            "warn",
            f"insufficient samples total={total} (<{min_samples})",
        )

    if fallback_rate >= threshold:
        return CheckResult(
            "plan-observe",
            "fail",
            f"fallback_rate={fallback_rate:.3f} >= threshold={threshold:.3f}",
        )

    return CheckResult(
        "plan-observe",
        "pass",
        f"fallback_rate={fallback_rate:.3f} threshold={threshold:.3f} total={total}",
    )


def check_plan_dispatch_replay() -> CheckResult:
    drift_window = os.getenv("PLAN_DISPATCH_REPLAY_DRIFT_WINDOW", "14")
    drift_min_samples = os.getenv("PLAN_DISPATCH_REPLAY_DRIFT_MIN_SAMPLES", "5")
    allowed_drift = os.getenv("PLAN_DISPATCH_REPLAY_ALLOWED_DRIFT", "0.20")
    complexity_drift = os.getenv("PLAN_DISPATCH_REPLAY_COMPLEXITY_DRIFT", "0.25")
    code, out, err = run_command(
        [
            "python3",
            "core/system/plan_dispatch_replay.py",
            "--limit",
            "30",
            "--min-complexity",
            "medium",
            "--drift-window",
            drift_window,
            "--drift-min-samples",
            drift_min_samples,
            "--allowed-rate-drift-threshold",
            allowed_drift,
            "--complexity-rate-drift-threshold",
            complexity_drift,
            "--append-report",
            "--json",
        ]
    )
    if code != 0:
        short = (err or out or "plan_dispatch_replay failed").splitlines()
        msg = (short[-1] if short else "plan_dispatch_replay failed")[:180]
        return CheckResult("plan-replay", "warn", msg)

    try:
        payload = parse_json_output(out)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("plan-replay", "warn", f"invalid json ({exc})")

    total = int(payload.get("total", 0))
    allowed_rate = float(payload.get("allowed_rate", 0.0))
    if total <= 0:
        return CheckResult("plan-replay", "warn", "no replay tasks available")

    drift = payload.get("drift", {})
    if isinstance(drift, dict) and drift.get("detected") is True:
        reason = str(drift.get("reason", "threshold_exceeded"))
        allowed_delta = drift.get("allowed_delta")
        max_complexity_delta = drift.get("max_complexity_delta")
        detail = (
            f"drift detected reason={reason} "
            f"allowed_delta={allowed_delta} "
            f"max_complexity_delta={max_complexity_delta}"
        )
        if os.getenv("PLAN_DISPATCH_REPLAY_DRIFT_FAIL", "0") == "1":
            return CheckResult("plan-replay", "fail", detail)
        return CheckResult("plan-replay", "warn", detail)

    return CheckResult(
        "plan-replay",
        "pass",
        f"total={total} allowed_rate={allowed_rate:.3f}",
    )


def check_plan_dispatch_daily_report() -> CheckResult:
    code, out, err = run_command(
        [
            "python3",
            "core/scripts/plan_dispatch_daily_report.py",
            "--write",
            "--json",
        ]
    )
    if code != 0:
        short = (err or out or "plan_dispatch_daily_report failed").splitlines()
        msg = (short[-1] if short else "plan_dispatch_daily_report failed")[:180]
        return CheckResult("plan-daily", "warn", msg)

    try:
        payload = parse_json_output(out)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("plan-daily", "warn", f"invalid json ({exc})")

    required = ("generated_at", "type", "metrics", "replay", "health", "report_path")
    missing = [key for key in required if key not in payload]
    if missing:
        return CheckResult("plan-daily", "warn", f"missing keys: {', '.join(missing)}")
    if payload.get("type") != "plan_dispatch_daily":
        return CheckResult("plan-daily", "warn", "invalid report type")

    report_path_raw = str(payload.get("report_path", "")).strip()
    if not report_path_raw:
        return CheckResult("plan-daily", "warn", "report_path empty")
    report_path = Path(report_path_raw)
    if not report_path.exists():
        return CheckResult("plan-daily", "warn", f"report file missing: {report_path}")

    health = payload.get("health", {})
    if not isinstance(health, dict):
        return CheckResult("plan-daily", "warn", "health section missing")
    status = str(health.get("status", "warn")).lower()
    issues = health.get("issues", [])
    warnings = health.get("warnings", [])
    issue_text = ", ".join(str(x) for x in (issues or []))[:180]
    warn_text = ", ".join(str(x) for x in (warnings or []))[:180]

    if status == "fail":
        detail = issue_text or "daily report health fail"
        return CheckResult("plan-daily", "fail", detail)
    if status == "warn":
        detail = warn_text or issue_text or "daily report health warn"
        return CheckResult("plan-daily", "warn", detail)

    metrics = payload.get("metrics", {})
    replay = payload.get("replay", {})
    fallback_rate = float(metrics.get("fallback_rate", 0.0)) if isinstance(metrics, dict) else 0.0
    allowed_rate = float(replay.get("allowed_rate", 0.0)) if isinstance(replay, dict) else 0.0
    return CheckResult(
        "plan-daily",
        "pass",
        f"fallback_rate={fallback_rate:.3f} allowed_rate={allowed_rate:.3f}",
    )


def check_plan_dispatch_pending_queue() -> CheckResult:
    try:
        max_age_hours = float(os.getenv("PLAN_DISPATCH_PENDING_MAX_AGE_HOURS", "24"))
    except Exception:
        max_age_hours = 24.0
    try:
        warn_count = int(os.getenv("PLAN_DISPATCH_PENDING_WARN_COUNT", "5"))
    except Exception:
        warn_count = 5
    code, out, err = run_command(
        [
            "python3",
            "core/scripts/plan_dispatch_pending_replay.py",
            "--dry-run",
            "--limit",
            "500",
            "--max-age-hours",
            str(max_age_hours),
            "--json",
        ]
    )
    if code != 0:
        short = (err or out or "plan_dispatch_pending_replay dry-run failed").splitlines()
        msg = (short[-1] if short else "plan_dispatch_pending_replay dry-run failed")[:180]
        return CheckResult("plan-pending", "warn", msg)

    try:
        payload = parse_json_output(out)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("plan-pending", "warn", f"invalid json ({exc})")

    try:
        open_total = int(payload.get("open_retryable_total", payload.get("open_total", 0)))
    except Exception:
        open_total = 0
    try:
        stale_total = int(payload.get("stale_total", 0))
    except Exception:
        stale_total = 0
    try:
        oldest_open_age = float(payload.get("oldest_open_age_hours", 0.0))
    except Exception:
        oldest_open_age = 0.0
    try:
        oldest_stale_age = float(payload.get("oldest_stale_age_hours", 0.0))
    except Exception:
        oldest_stale_age = 0.0

    if stale_total > 0:
        return CheckResult(
            "plan-pending",
            "fail",
            (
                f"stale_total={stale_total} "
                f"oldest_stale_age_hours={oldest_stale_age:.2f} "
                f"(max_age_hours={max_age_hours:.2f})"
            ),
        )

    if open_total >= max(1, warn_count):
        return CheckResult(
            "plan-pending",
            "warn",
            (
                f"open_retryable_total={open_total} "
                f">= warn_count={max(1, warn_count)} "
                f"oldest_open_age_hours={oldest_open_age:.2f}"
            ),
        )

    return CheckResult(
        "plan-pending",
        "pass",
        (
            f"open_retryable_total={open_total} "
            f"oldest_open_age_hours={oldest_open_age:.2f} "
            f"stale_total={stale_total}"
        ),
    )


def check_skill_tool_audit() -> CheckResult:
    code, out, err = run_command(["python3", "core/scripts/skill_tool_audit.py", "--json"])
    if code != 0 and not out:
        short = (err or "skill_tool_audit failed").splitlines()
        msg = (short[-1] if short else "skill_tool_audit failed")[:180]
        return CheckResult("skill-tool-audit", "fail", msg)
    try:
        payload = parse_json_output(out)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("skill-tool-audit", "fail", f"invalid json ({exc})")

    overall = str(payload.get("overall", "")).lower()
    score = payload.get("score")
    if overall == "pass":
        return CheckResult("skill-tool-audit", "pass", f"score={score}")
    if overall == "warn":
        return CheckResult("skill-tool-audit", "warn", f"score={score}")
    details = payload.get("summary", "audit reported failures")
    return CheckResult("skill-tool-audit", "fail", f"score={score} {details}")


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


def check_pipeline_resilience_smoke() -> CheckResult:
    code, out, err = run_command(["python3", "core/scripts/pipeline_resilience_smoke.py"])
    if code != 0:
        merged = f"{out}\n{err}".lower()
        if "queue not clean before smoke" in merged:
            return CheckResult("pipeline-smoke", "warn", "queue busy; smoke skipped")
        text = (err or out or "pipeline resilience smoke failed").splitlines()
        short = (text[-1] if text else "pipeline resilience smoke failed")[:180]
        return CheckResult("pipeline-smoke", "fail", short)

    try:
        payload = parse_json_output(out)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("pipeline-smoke", "warn", f"invalid json ({exc})")

    tasks = payload.get("tasks", {})
    if not isinstance(tasks, dict):
        return CheckResult("pipeline-smoke", "fail", "tasks payload missing")

    sa_mode = (tasks.get("sa") or {}).get("analysis_mode")
    ce_mode = (tasks.get("ce") or {}).get("analysis_mode")
    ce_status = (tasks.get("ce") or {}).get("status")
    cd_mode = (tasks.get("cd") or {}).get("review_mode")
    cd_decision = (tasks.get("cd") or {}).get("decision")
    queue_after = payload.get("queue_after", {})
    pending = int((queue_after or {}).get("pending", -1))
    processing = int((queue_after or {}).get("processing", -1))

    if sa_mode != "fallback_local":
        return CheckResult("pipeline-smoke", "fail", f"sa_mode={sa_mode}")
    if ce_mode != "fallback_local" or ce_status != "draft_for_cd":
        return CheckResult("pipeline-smoke", "fail", f"ce_mode={ce_mode} ce_status={ce_status}")
    if cd_mode != "fallback_local" or cd_decision not in {"approve", "revise", "reject"}:
        return CheckResult("pipeline-smoke", "fail", f"cd_mode={cd_mode} decision={cd_decision}")
    if pending != 0 or processing != 0:
        return CheckResult("pipeline-smoke", "fail", f"queue_after pending={pending} processing={processing}")

    return CheckResult(
        "pipeline-smoke",
        "pass",
        f"sa/ce/cd fallback chain ok (decision={cd_decision})",
    )


def check_git_hook_automation() -> CheckResult:
    code, out, _ = run_command(["git", "config", "--get", "core.hooksPath"])
    hooks_path = out.strip() if code == 0 else ""
    if hooks_path != "core/scripts/hooks":
        return CheckResult("git-hooks", "fail", f"core.hooksPath={hooks_path or '(unset)'}")

    required = (
        PROJECT_ROOT / "core/scripts/hooks/pre-commit",
        PROJECT_ROOT / "core/scripts/hooks/pre-push",
        PROJECT_ROOT / "core/scripts/hooks/post-commit",
        PROJECT_ROOT / "core/scripts/hooks/trigger_autodeploy.sh",
    )
    missing = [str(p.relative_to(PROJECT_ROOT)) for p in required if not p.exists()]
    if missing:
        return CheckResult("git-hooks", "fail", f"missing: {', '.join(missing)}")

    auto_deploy = (run_command(["git", "config", "--get", "woohwahae.autodeploy"])[1] or "").strip().lower()
    branch = (run_command(["git", "config", "--get", "woohwahae.autodeployBranch"])[1] or "").strip()
    target = (run_command(["git", "config", "--get", "woohwahae.autodeployTarget"])[1] or "").strip()
    prepush_mode = (run_command(["git", "config", "--get", "woohwahae.prepushMode"])[1] or "").strip()

    if auto_deploy != "true":
        return CheckResult("git-hooks", "warn", "autodeploy disabled")

    if not branch:
        branch = "main(default)"
    if not target:
        target = "all(default)"
    if not prepush_mode:
        prepush_mode = "lite(default)"

    return CheckResult(
        "git-hooks",
        "pass",
        f"autodeploy=true branch={branch} target={target} prepush={prepush_mode}",
    )


def check_token_efficiency() -> CheckResult:
    """토큰 효율 지표 — 복합 점수 + 주요 수치 요약."""
    try:
        import importlib.util as ilu
        spec = ilu.spec_from_file_location(
            "efficiency_report",
            PROJECT_ROOT / "core/scripts/efficiency_report.py",
        )
        mod = ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)

        last = 100  # 최근 100건 기준
        disp = mod.dispatch_efficiency(last)
        cncl = mod.council_efficiency(last)
        doc  = mod.doctor_trend(10)
        comp = mod.composite_score(disp, cncl, doc)

        score_val    = comp.get("composite", 0)
        grade        = comp.get("grade", "unknown")
        fallback_pct = disp.get("fallback_rate_pct", 0)
        degraded_pct = cncl.get("wasted_council_calls_pct", 0)
        dead_pct     = cncl.get("clarification_dead_pct", 0)

        detail = (
            f"composite={score_val:.0f}/100 [{grade}] "
            f"fallback={fallback_pct:.1f}% "
            f"council_waste={degraded_pct:.1f}% "
            f"clarify_dead={dead_pct:.1f}%"
        )

        if grade in ("excellent", "good"):
            status = "pass"
        elif grade == "fair":
            status = "warn"
        else:
            status = "fail"

        return CheckResult("token-efficiency", status, detail)
    except Exception as exc:
        return CheckResult("token-efficiency", "warn", f"계산 실패: {exc}")


def check_tests(run_tests: bool) -> CheckResult:
    if not run_tests:
        return CheckResult("tests", "warn", "skipped (--run-tests not set)")

    env = dict(**{"LAYER_DISABLE_FILESYSTEM_GUARD": "1"}, **dict())
    code, out, err = subprocess_run_with_env(
        [
            "pytest",
            "-q",
            "core/tests/test_queue_manager.py",
            "core/tests/test_handoff.py",
            "core/tests/test_plan_dispatch_classifier.py",
            "core/tests/test_plan_dispatch_smoke.py",
            "core/tests/test_plan_dispatch_metrics.py",
            "core/tests/test_plan_dispatch_replay.py",
            "core/tests/test_plan_dispatch_daily_report.py",
            "core/tests/test_plan_dispatch_pending_replay.py",
            "core/tests/test_monitor_dashboard.py",
            "core/tests/test_harness_doctor_asset_registry.py",
            "core/tests/test_harness_doctor_council_worker.py",
            "core/tests/test_progress_graph.py",
        ],
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
    if not results:
        return 0
    earned = sum(2 if r.status == "pass" else 1 if r.status == "warn" else 0 for r in results)
    total = len(results) * 2
    return round(earned / total * 100)


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
    if build_progress_payload is not None:
        try:
            trend = build_progress_payload(limit=30, graph_width=24)
            graphs = trend.get("graphs", {})
            metrics = trend.get("metrics", {})
            print("Progress Trend:")
            print(
                "  score     "
                f"{graphs.get('score', '·')} "
                f"{float(metrics.get('score', {}).get('latest', 0.0)):.1f}"
            )
            print(
                "  fallback  "
                f"{graphs.get('fallback_rate', '·')} "
                f"{float(metrics.get('fallback_rate', {}).get('latest', 0.0))*100:.1f}%"
            )
            print(
                "  blocked   "
                f"{graphs.get('blocked_rate', '·')} "
                f"{float(metrics.get('blocked_rate', {}).get('latest', 0.0))*100:.1f}%"
            )
        except Exception:
            pass
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
        check_council_worker(),
        check_plan_dispatch(),
        check_plan_dispatch_observability(),
        check_plan_dispatch_replay(),
        check_plan_dispatch_daily_report(),
        check_plan_dispatch_pending_queue(),
        check_skill_tool_audit(),
        check_model_role_routing(),
        check_pipeline_resilience_smoke(),
        check_git_hook_automation(),
        check_work_lock(),
        check_asset_registry_integrity(),
        check_token_efficiency(),
        check_tests(args.run_tests),
    ]

    readiness_score = score(results)
    overall = overall_status(results, readiness_score)
    append_report(results, readiness_score, overall)
    print_report(results, readiness_score, overall)
    return 0 if overall == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
