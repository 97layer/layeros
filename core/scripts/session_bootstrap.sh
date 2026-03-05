#!/usr/bin/env bash
# LAYER OS Session Bootstrap - strict runtime gate

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "BLOCKED missing: python3"
  exit 1
fi

python3 - <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional


ROOT = Path.cwd()
CONTRACT_PATH = ROOT / "knowledge" / "system" / "agent_runtime_contract.json"

issues: List[str] = []


def add_issue(message: str) -> None:
    issues.append(f"BLOCKED {message}")


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        add_issue(f"invalid json: {path.relative_to(ROOT)} ({exc})")
        return None


def ensure_file(relpath: str) -> Optional[Path]:
    path = ROOT / relpath
    if not path.is_file():
        add_issue(f"missing: {relpath}")
        return None
    return path


def parse_json_tail(text: str) -> Optional[dict]:
    for raw in reversed((text or "").splitlines()):
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


if not CONTRACT_PATH.is_file():
    add_issue("missing: knowledge/system/agent_runtime_contract.json")
    for issue in issues:
        print(issue)
    print("BLOCKED")
    sys.exit(1)

contract = read_json(CONTRACT_PATH)
if contract is None:
    for issue in issues:
        print(issue)
    print("BLOCKED")
    sys.exit(1)

required_files = contract.get("required_files", [])
required_skills = contract.get("required_skills", [])
required_markers: Dict[str, List[str]] = contract.get("required_markers", {})
proactive_rule_file = contract.get("proactive_rule_file", ".claude/rules/proactive-tools.md")
anti_hallucination_rule_file = contract.get("anti_hallucination_rule_file", ".claude/rules/anti-hallucination.md")
plan_council_file = contract.get("plan_council_file", "core/system/plan_council.py")
plan_dispatch_file = contract.get("plan_dispatch_file", "core/scripts/plan_dispatch.sh")
plan_council_hook_file = contract.get("plan_council_hook_file", ".claude/hooks/plan-council.sh")
plan_council_rule_file = contract.get("plan_council_rule_file", ".claude/rules/plan-council.md")
model_role_rule_file = contract.get("model_role_rule_file", ".claude/rules/model-role-routing.md")
plan_council_report_file = contract.get("plan_council_report_file", "knowledge/system/plan_council_reports.jsonl")
required_proactive_tools = contract.get("required_proactive_tools", [])
lock_file = contract.get("lock_file", "knowledge/system/web_work_lock.json")
evidence_log_file = contract.get("evidence_log_file", "knowledge/system/evidence_log.jsonl")
optional_lock_files = contract.get("optional_lock_files", [])
anti_hallucination_contract = contract.get("anti_hallucination_contract", {})
plan_council_contract = contract.get("plan_council_contract", {})
plan_dispatch_contract = contract.get("plan_dispatch_contract", {})
model_role_contract = contract.get("model_role_contract", {})

for relpath in required_files:
    ensure_file(relpath)

for skill_path in required_skills:
    if not Path(skill_path).is_file():
        add_issue(f"missing: {skill_path}")

for relpath, markers in required_markers.items():
    path = ensure_file(relpath)
    if path is None:
        continue
    content = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in content:
            add_issue(f"missing marker: '{marker}' in {relpath}")

proactive_path = ensure_file(proactive_rule_file)
if proactive_path is not None:
    proactive_content = proactive_path.read_text(encoding="utf-8")
    for tool_name in required_proactive_tools:
        if tool_name not in proactive_content:
            add_issue(f"missing proactive trigger: '{tool_name}' in {proactive_rule_file}")

anti_rule_path = ensure_file(anti_hallucination_rule_file)
if anti_rule_path is not None:
    anti_rule_content = anti_rule_path.read_text(encoding="utf-8")
    if "근거가 없으면 추측하지 않는다" not in anti_rule_content:
        add_issue(
            "missing anti-hallucination core marker: '근거가 없으면 추측하지 않는다' "
            f"in {anti_hallucination_rule_file}"
        )

plan_rule_path = ensure_file(plan_council_rule_file)
if plan_rule_path is not None:
    plan_rule_content = plan_rule_path.read_text(encoding="utf-8")
    if "Claude + Gemini" not in plan_rule_content:
        add_issue(
            "missing plan-council core marker: 'Claude + Gemini' "
            f"in {plan_council_rule_file}"
        )

model_role_path = ensure_file(model_role_rule_file)
if model_role_path is not None:
    model_role_content = model_role_path.read_text(encoding="utf-8")
    for marker in ("Claude", "Codex", "Gemini"):
        if marker not in model_role_content:
            add_issue(f"missing model-role marker: '{marker}' in {model_role_rule_file}")

required_contract_flags = [
    "require_evidence_for_facts",
    "forbid_guessing",
    "require_unknown_when_unverified",
    "require_absolute_dates_for_relative_time",
    "require_fresh_verification_for_time_sensitive",
]
if not isinstance(anti_hallucination_contract, dict):
    add_issue("invalid contract: anti_hallucination_contract must be object")
else:
    for flag in required_contract_flags:
        if anti_hallucination_contract.get(flag) is not True:
            add_issue(f"invalid contract flag: anti_hallucination_contract.{flag} must be true")

required_plan_flags = [
    "enabled",
    "require_hook",
    "require_both_models",
    "require_preflight_for_nontrivial",
]
if not isinstance(plan_council_contract, dict):
    add_issue("invalid contract: plan_council_contract must be object")
else:
    for flag in required_plan_flags:
        if plan_council_contract.get(flag) is not True:
            add_issue(f"invalid contract flag: plan_council_contract.{flag} must be true")

required_dispatch_flags = [
    "enabled",
    "default_mode_auto",
    "allow_manual",
    "require_dispatch_for_nontrivial",
]
if not isinstance(plan_dispatch_contract, dict):
    add_issue("invalid contract: plan_dispatch_contract must be object")
else:
    for flag in required_dispatch_flags:
        if plan_dispatch_contract.get(flag) is not True:
            add_issue(f"invalid contract flag: plan_dispatch_contract.{flag} must be true")

if not isinstance(model_role_contract, dict):
    add_issue("invalid contract: model_role_contract must be object")
else:
    expected_roles = {
        "planner": "claude",
        "coder": "codex",
        "verifier": "gemini",
    }
    for key, expected in expected_roles.items():
        if str(model_role_contract.get(key, "")).lower() != expected:
            add_issue(f"invalid model role: model_role_contract.{key} must be '{expected}'")
    if model_role_contract.get("forbid_role_inversion") is not True:
        add_issue("invalid contract flag: model_role_contract.forbid_role_inversion must be true")

required_lock_path = ensure_file(lock_file)
if required_lock_path is not None:
    read_json(required_lock_path)

for relpath in optional_lock_files:
    optional_path = ROOT / relpath
    if optional_path.exists():
        read_json(optional_path)

plan_report_path = ensure_file(plan_council_report_file)
if plan_report_path is not None:
    for lineno, raw in enumerate(plan_report_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            json.loads(line)
        except Exception as exc:  # noqa: BLE001
            add_issue(
                f"invalid jsonl: {plan_council_report_file}:{lineno} ({exc})"
            )

evidence_path = ensure_file(evidence_log_file)
if evidence_path is not None:
    for lineno, raw in enumerate(evidence_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            json.loads(line)
        except Exception as exc:  # noqa: BLE001
            add_issue(
                f"invalid jsonl: {evidence_log_file}:{lineno} ({exc})"
            )

evidence_guard_script = ROOT / "core" / "system" / "evidence_guard.py"
if evidence_guard_script.is_file():
    proc = subprocess.run(
        [sys.executable, str(evidence_guard_script), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or "READY" not in proc.stdout:
        output = (proc.stdout + proc.stderr).strip() or "no output"
        add_issue(f"evidence_guard check failed: {output}")

agents_guardrail_trace_script = ROOT / "core" / "system" / "agents_guardrail_trace.py"
if agents_guardrail_trace_script.is_file():
    proc = subprocess.run(
        [sys.executable, str(agents_guardrail_trace_script), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or "READY" not in proc.stdout:
        output = (proc.stdout + proc.stderr).strip() or "no output"
        add_issue(f"agents_guardrail_trace check failed: {output}")

plan_council_path = ensure_file(plan_council_file)
plan_dispatch_path = ensure_file(plan_dispatch_file)
ensure_file(plan_council_hook_file)
if plan_council_path is not None:
    args = [sys.executable, str(plan_council_path), "--self-check"]
    if isinstance(plan_council_contract, dict) and plan_council_contract.get("require_both_models"):
        args.append("--require-both")
    proc = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or "READY" not in proc.stdout:
        output = (proc.stdout + proc.stderr).strip() or "no output"
        add_issue(f"plan_council check failed: {output}")
    elif (
        isinstance(plan_council_contract, dict)
        and plan_council_contract.get("require_preflight_for_nontrivial")
    ):
        allow_degraded = str(os.getenv("SESSION_BOOTSTRAP_ALLOW_DEGRADED", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        probe_proc = subprocess.run(
            [
                sys.executable,
                str(plan_council_path),
                "--task",
                "session bootstrap council reachability probe",
                "--mode",
                "preflight",
                "--json",
                "--no-save",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        probe_payload = parse_json_tail(probe_proc.stdout)
        consensus = probe_payload.get("consensus", {}) if isinstance(probe_payload, dict) else {}
        status = str(consensus.get("status", "")).strip().lower() if isinstance(consensus, dict) else ""
        models_used = {
            str(item).strip().lower()
            for item in (consensus.get("models_used", []) if isinstance(consensus, dict) else [])
            if str(item).strip()
        }

        if not status:
            probe_out = (probe_proc.stdout + probe_proc.stderr).strip() or "no output"
            add_issue(f"plan_council preflight probe parse failed: {probe_out}")
        else:
            if status != "ready" and not allow_degraded:
                add_issue(f"plan_council preflight degraded: status={status} models_used={sorted(models_used)}")
            if plan_council_contract.get("require_both_models") and not {"claude", "gemini"}.issubset(models_used):
                if not allow_degraded:
                    add_issue(
                        "plan_council preflight missing required models: "
                        f"models_used={sorted(models_used)}"
                    )

if plan_dispatch_path is not None:
    smoke_nontrivial_task = "스킬 및 기본 툴 체계를 분석하고 업그레이드 항목을 구현한다"
    smoke_manual_task = (
        "다중 파일 웹 개편 작업: website/archive/index.html, website/practice/index.html, "
        "website/lab/index.html의 레이아웃 간격/타이포 일관성만 조정하고 "
        "about 텍스트 및 백엔드/인프라는 변경하지 않는다. "
        "변경 후 visual_validator와 build_components로 검증한다."
    )
    smoke_cases = [
        ("auto-simple", "ok", "--auto"),
        ("auto-nontrivial", smoke_nontrivial_task, "--auto"),
        ("manual", smoke_manual_task, "--manual"),
    ]
    for label, task_text, mode_flag in smoke_cases:
        proc = subprocess.run(
            ["bash", str(plan_dispatch_path), task_text, mode_flag, "--smoke"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode != 0:
            output = (proc.stdout + proc.stderr).strip() or "no output"
            add_issue(f"plan_dispatch {label} check failed: {output}")
            continue

        parsed = None
        try:
            parsed = json.loads((proc.stdout or "").strip())
        except Exception as exc:  # noqa: BLE001
            add_issue(f"plan_dispatch {label} output parse failed: {exc}")
            continue

        if not isinstance(parsed, dict):
            add_issue(f"plan_dispatch {label} output must be object")
            continue

        consensus = parsed.get("consensus")
        dispatcher = parsed.get("dispatcher")
        if not isinstance(consensus, dict):
            add_issue(f"plan_dispatch {label} missing consensus object")
        if not isinstance(dispatcher, dict):
            add_issue(f"plan_dispatch {label} missing dispatcher object")
            continue

        if label == "auto-simple":
            if dispatcher.get("executed") is not False:
                add_issue("plan_dispatch auto-simple must remain skip path")
            if dispatcher.get("reason") != "simple_task":
                add_issue("plan_dispatch auto-simple must report reason=simple_task")

        if label == "auto-nontrivial":
            if dispatcher.get("executed") is not True:
                add_issue("plan_dispatch auto-nontrivial must execute council path")
            if dispatcher.get("complexity") not in {"medium", "high"}:
                add_issue("plan_dispatch auto-nontrivial complexity must be medium/high")

        if label == "manual" and dispatcher.get("executed") is not True:
            add_issue("plan_dispatch manual must execute council path")

if issues:
    for issue in issues:
        print(issue)
    print("BLOCKED")
    sys.exit(1)

print("READY")
PY

bootstrap_rc=$?
if [ $bootstrap_rc -ne 0 ]; then
  exit $bootstrap_rc
fi

python3 core/system/session_state.py \
  --event start \
  --agent-id "${SESSION_AGENT_ID:-Codex}" \
  --task-label "${SESSION_TASK_LABEL:-session-bootstrap}" \
  --session-id "${SESSION_ID:-}" >/dev/null 2>&1 || true

exit 0
