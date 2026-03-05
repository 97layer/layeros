#!/usr/bin/env python3
"""
plan_council.py - Pre-execution planning council (Claude + Gemini).

Purpose:
- Build an evidence-oriented execution plan before non-trivial implementation.
- Collect perspectives from both Claude and Gemini, then merge to consensus.
- Persist council records for auditability.

Usage:
  python3 core/system/plan_council.py --self-check --require-both
  python3 core/system/plan_council.py --task "..." --mode preflight --json
  python3 core/system/plan_council.py --task "..." --mode hook
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_RETRY_COUNT = int(os.getenv("PLAN_COUNCIL_RETRIES", "3"))
_RETRY_DELAY = float(os.getenv("PLAN_COUNCIL_RETRY_DELAY", "2.0"))
_RUNTIME_TTL_SECONDS = max(60, int(os.getenv("PLAN_COUNCIL_TTL_SECONDS", "600")))
_STABILITY_WINDOW = max(3, int(os.getenv("PLAN_COUNCIL_STABILITY_WINDOW", "8")))
_MIN_RELIABILITY = float(os.getenv("PLAN_COUNCIL_MIN_RELIABILITY", "0.65"))
_NETCHECK_ENABLED = os.getenv("PLAN_COUNCIL_NETCHECK", "1").lower() in {"1", "true", "yes"}
_NETCHECK_TIMEOUT = max(0.5, float(os.getenv("PLAN_COUNCIL_NETCHECK_TIMEOUT", "2.5")))


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_FILE = PROJECT_ROOT / "knowledge" / "system" / "plan_council_reports.jsonl"

DEFAULT_GEMINI_MODEL = os.getenv("PLAN_COUNCIL_GEMINI_MODEL", "gemini-2.5-flash")
DEFAULT_CLAUDE_MODEL = os.getenv("PLAN_COUNCIL_CLAUDE_MODEL", "claude-sonnet-4-5")
_NETCHECK_TARGETS = [
    ("generativelanguage.googleapis.com", 443),
    ("api.anthropic.com", 443),
]


def _load_env_defaults() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    try:
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key:
                os.environ.setdefault(key, value)
    except Exception:
        # Non-fatal. Runtime may still use externally injected env vars.
        return


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None

    fenced = re.search(r"```json\s*([\s\S]+?)\s*```", raw)
    if fenced:
        raw = fenced.group(1).strip()
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start : end + 1]

    try:
        obj = json.loads(raw)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _normalize_list(value: Any, limit: int = 6) -> List[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = [value]
    else:
        items = []

    normalized: List[str] = []
    for item in items:
        s = str(item).strip()
        if not s:
            continue
        if s not in normalized:
            normalized.append(s)
        if len(normalized) >= limit:
            break
    return normalized


def _normalize_plan(raw: Dict[str, Any]) -> Dict[str, Any]:
    decision = str(raw.get("decision", "")).strip().lower()
    if decision not in {"go", "needs_clarification"}:
        decision = "go"

    return {
        "intent": str(raw.get("intent", "")).strip(),
        "approach": str(raw.get("approach", "")).strip(),
        "steps": _normalize_list(raw.get("steps", []), limit=6),
        "risks": _normalize_list(raw.get("risks", []), limit=5),
        "checks": _normalize_list(raw.get("checks", []), limit=6),
        "tools": _normalize_list(raw.get("tools", []), limit=6),
        "decision": decision,
    }


def _merge_unique(*lists: List[str], limit: int = 8) -> List[str]:
    merged: List[str] = []
    for lst in lists:
        for item in lst:
            if item and item not in merged:
                merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _network_probe() -> Dict[str, Any]:
    """
    Lightweight DNS/TCP probe for model endpoints.
    Used only as diagnostic metadata when both models fail.
    """
    results: List[Dict[str, Any]] = []
    for host, port in _NETCHECK_TARGETS:
        dns_ok = False
        tcp_ok = False
        dns_error = ""
        tcp_error = ""

        try:
            socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            dns_ok = True
        except Exception as exc:  # noqa: BLE001
            dns_error = str(exc)

        if dns_ok:
            try:
                with socket.create_connection((host, port), timeout=_NETCHECK_TIMEOUT):
                    tcp_ok = True
            except Exception as exc:  # noqa: BLE001
                tcp_error = str(exc)

        results.append(
            {
                "host": host,
                "port": port,
                "dns_ok": dns_ok,
                "dns_error": dns_error,
                "tcp_ok": tcp_ok,
                "tcp_error": tcp_error,
            }
        )

    return {
        "timeout_sec": _NETCHECK_TIMEOUT,
        "results": results,
        "all_dns_ok": all(item.get("dns_ok") for item in results),
        "any_tcp_ok": any(item.get("tcp_ok") for item in results),
    }


def _score_from_status(status: str, models_used: List[str]) -> float:
    normalized = str(status or "").strip().lower()
    models = [str(m).strip().lower() for m in (models_used or []) if str(m).strip()]

    if normalized == "ready":
        return 1.0 if len(models) >= 2 else 0.85
    if normalized == "degraded":
        if not models:
            return 0.0
        if "offline" in models:
            return 0.25
        if len(models) == 1:
            return 0.55
        return 0.45
    if normalized == "smoke":
        return 1.0
    if normalized == "skipped":
        return 0.8
    return 0.5


def _load_recent_consensus(limit: int) -> List[Dict[str, Any]]:
    if limit <= 0 or not REPORT_FILE.exists():
        return []

    rows: List[Dict[str, Any]] = []
    try:
        for raw in REPORT_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            consensus = obj.get("consensus")
            if not isinstance(consensus, dict):
                continue
            rows.append(
                {
                    "status": str(consensus.get("status", "")).strip().lower(),
                    "models_used": consensus.get("models_used", []),
                    "decision": str(consensus.get("decision", "go")).strip().lower(),
                }
            )
            if len(rows) > limit:
                rows = rows[-limit:]
    except Exception:
        return []
    return rows


def _build_runtime_meta(
    *,
    task: str,
    timestamp: str,
    consensus: Dict[str, Any],
    claude_ok: bool,
    gemini_ok: bool,
    claude_error: str,
    gemini_error: str,
) -> Dict[str, Any]:
    models_used = [str(m).strip().lower() for m in consensus.get("models_used", []) if str(m).strip()]
    status = str(consensus.get("status", "")).strip().lower()
    decision = str(consensus.get("decision", "go")).strip().lower()

    if claude_ok and gemini_ok:
        availability_score = 1.0
    elif claude_ok or gemini_ok:
        availability_score = 0.5
    else:
        availability_score = 0.0

    history = _load_recent_consensus(_STABILITY_WINDOW)
    history_scores: List[float] = []
    ready_count = 0
    dual_model_count = 0
    transitions = 0
    previous_status = ""

    for item in history:
        hist_status = str(item.get("status", "")).strip().lower()
        hist_models = item.get("models_used", [])
        hist_models_norm = [str(m).strip().lower() for m in (hist_models if isinstance(hist_models, list) else [])]
        history_scores.append(_score_from_status(hist_status, hist_models_norm))
        if hist_status == "ready":
            ready_count += 1
        if len(hist_models_norm) >= 2:
            dual_model_count += 1
        if previous_status and hist_status != previous_status:
            transitions += 1
        previous_status = hist_status

    history_len = len(history_scores)
    if history_len > 0:
        history_avg = sum(history_scores) / history_len
        ready_ratio = ready_count / history_len
        dual_model_ratio = dual_model_count / history_len
        flip_ratio = transitions / max(1, history_len - 1)
        stability_score = _clamp((history_avg * 0.55) + (ready_ratio * 0.25) + ((1.0 - flip_ratio) * 0.20))
    else:
        history_avg = availability_score
        ready_ratio = 1.0 if availability_score == 1.0 else 0.0
        dual_model_ratio = 1.0 if availability_score == 1.0 else 0.0
        flip_ratio = 0.0
        stability_score = availability_score

    current_score = _score_from_status(status, models_used)
    reliability_score = _clamp((current_score * 0.70) + (stability_score * 0.30))

    if reliability_score >= 0.8:
        reliability_tier = "high"
    elif reliability_score >= _MIN_RELIABILITY:
        reliability_tier = "medium"
    else:
        reliability_tier = "low"

    unstable = bool(flip_ratio >= 0.45 or stability_score < 0.55)

    if decision == "needs_clarification":
        gate_recommendation = "needs_clarification"
    elif availability_score <= 0.0:
        # 네트워크 오류 — 작업 자체 위험이 아니므로 caution으로 다운그레이드
        gate_recommendation = "caution"
    elif status == "degraded" or reliability_score < _MIN_RELIABILITY or unstable:
        gate_recommendation = "caution"
    else:
        gate_recommendation = "go"

    council_seed = f"{timestamp}|{task}|{','.join(models_used)}"
    council_id = hashlib.sha1(council_seed.encode("utf-8")).hexdigest()[:12]
    generated_at = datetime.now(timezone.utc)
    expires_at = generated_at + timedelta(seconds=_RUNTIME_TTL_SECONDS)

    return {
        "council_id": council_id,
        "generated_at_utc": generated_at.isoformat(),
        "expires_at_utc": expires_at.isoformat(),
        "ttl_seconds": _RUNTIME_TTL_SECONDS,
        "required_models": ["claude", "gemini"],
        "models_ok": {
            "claude": claude_ok,
            "gemini": gemini_ok,
        },
        "model_errors": {
            "claude": claude_error or "",
            "gemini": gemini_error or "",
        },
        "availability_score": round(availability_score, 3),
        "current_score": round(current_score, 3),
        "stability_score": round(stability_score, 3),
        "historical_average_score": round(history_avg, 3),
        "ready_ratio": round(ready_ratio, 3),
        "dual_model_ratio": round(dual_model_ratio, 3),
        "flip_ratio": round(flip_ratio, 3),
        "stability_window": history_len,
        "reliability_score": round(reliability_score, 3),
        "reliability_tier": reliability_tier,
        "unstable": unstable,
        "gate_recommendation": gate_recommendation,
        "status_stamp": {
            "status": status,
            "models_used": models_used,
            "decision": decision,
            "timestamp": timestamp,
        },
    }


def _build_prompt(task: str) -> str:
    return (
        "당신은 실행 전 계획 협의 에이전트다.\n"
        "요구사항을 바로 구현하지 말고, 리스크와 검증을 먼저 구조화하라.\n\n"
        f"[요청]\n{task}\n\n"
        "아래 JSON 객체만 반환하라:\n"
        "{\n"
        '  "intent": "요청의 본질(1문장)",\n'
        '  "approach": "핵심 접근(1~2문장)",\n'
        '  "steps": ["실행 단계 1", "실행 단계 2"],\n'
        '  "risks": ["리스크 1", "리스크 2"],\n'
        '  "checks": ["검증 1", "검증 2"],\n'
        '  "tools": ["필요 도구 1", "필요 도구 2"],\n'
        '  "decision": "go 또는 needs_clarification"\n'
        "}\n\n"
        "제약:\n"
        "- steps 최대 6개\n"
        "- risks 최대 5개\n"
        "- checks는 실행 가능한 검증으로 작성\n"
        "- 설명문/마크다운/코드블록 없이 JSON만 출력\n"
    )


def _call_gemini(task: str) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        import google.genai as genai
    except Exception as exc:  # noqa: BLE001
        return None, f"gemini import failed: {exc}"

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None, "gemini key missing"

    last_err = ""
    for attempt in range(1, _RETRY_COUNT + 1):
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=DEFAULT_GEMINI_MODEL,
                contents=[_build_prompt(task)],
            )
            text = getattr(response, "text", "") or ""
            parsed = _extract_json(text)
            if not parsed:
                return None, "gemini parse failed"
            return _normalize_plan(parsed), ""
        except Exception as exc:  # noqa: BLE001
            last_err = f"gemini call failed: {exc}"
            if attempt < _RETRY_COUNT:
                time.sleep(_RETRY_DELAY)
    return None, last_err


def _call_claude(task: str) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        import anthropic
    except Exception as exc:  # noqa: BLE001
        return None, f"claude import failed: {exc}"

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None, "claude key missing"

    last_err = ""
    for attempt in range(1, _RETRY_COUNT + 1):
        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=DEFAULT_CLAUDE_MODEL,
                max_tokens=900,
                messages=[{"role": "user", "content": _build_prompt(task)}],
            )
            chunks: List[str] = []
            for block in getattr(message, "content", []):
                block_text = getattr(block, "text", "")
                if block_text:
                    chunks.append(block_text)
            text = "\n".join(chunks).strip()
            parsed = _extract_json(text)
            if not parsed:
                return None, "claude parse failed"
            return _normalize_plan(parsed), ""
        except Exception as exc:  # noqa: BLE001
            last_err = f"claude call failed: {exc}"
            if attempt < _RETRY_COUNT:
                time.sleep(_RETRY_DELAY)
    return None, last_err


def _build_consensus(
    task: str,
    claude_plan: Optional[Dict[str, Any]],
    gemini_plan: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    intent = ""
    approach = ""
    sources: List[str] = []

    if claude_plan:
        sources.append("claude")
        intent = claude_plan.get("intent", "")
        approach = claude_plan.get("approach", "")
    if gemini_plan:
        sources.append("gemini")
        if not intent:
            intent = gemini_plan.get("intent", "")
        if not approach:
            approach = gemini_plan.get("approach", "")

    fallback = False
    if not sources and os.getenv("PLAN_COUNCIL_OFFLINE_FALLBACK", "0").lower() in {"1", "true", "yes"}:
        # 네트워크 불가 환경에서도 최소 계획을 허용하기 위한 옵트인 오프라인 모드
        sources.append("offline")
        fallback = True

    steps = _merge_unique(
        claude_plan.get("steps", []) if claude_plan else [],
        gemini_plan.get("steps", []) if gemini_plan else [],
        limit=6,
    )
    risks = _merge_unique(
        claude_plan.get("risks", []) if claude_plan else [],
        gemini_plan.get("risks", []) if gemini_plan else [],
        limit=5,
    )
    checks = _merge_unique(
        claude_plan.get("checks", []) if claude_plan else [],
        gemini_plan.get("checks", []) if gemini_plan else [],
        limit=6,
    )
    tools = _merge_unique(
        claude_plan.get("tools", []) if claude_plan else [],
        gemini_plan.get("tools", []) if gemini_plan else [],
        limit=6,
    )

    claude_decision = claude_plan.get("decision") if claude_plan else ""
    gemini_decision = gemini_plan.get("decision") if gemini_plan else ""
    decisions = [d for d in [claude_decision, gemini_decision] if d]
    decision = "go"
    conflict = False
    if decisions:
        decision = "needs_clarification" if "needs_clarification" in decisions else "go"
        conflict = len(set(decisions)) > 1

    if not steps:
        steps = [
            "요청을 작업 단위로 분해한다",
            "관련 파일/의존성 맥락을 확인한다",
            "변경 구현 후 검증을 수행한다",
        ]
    if not checks:
        checks = [
            "핵심 스크립트/테스트를 실행해 실패 여부 확인",
            "변경 파일 diff 검토로 부수효과 확인",
        ]

    status = "ready"
    if fallback or not sources:
        status = "degraded"
        intent = intent or task[:120]
        approach = approach or "모델 협의 미가용 상태로 로컬 규칙 기반 최소 계획 적용"
    elif len(sources) == 1:
        status = "degraded"

    return {
        "status": status,
        "models_used": sources,
        "planner_primary": "claude",
        "verifier_secondary": "gemini",
        "intent": intent or task[:120],
        "approach": approach or "요청 기반 단계적 구현",
        "steps": steps,
        "risks": risks,
        "checks": checks,
        "tools": tools,
        "decision": decision,
        "decision_conflict": conflict,
    }


def _append_report(payload: Dict[str, Any]) -> None:
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_FILE.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def run_council(task: str, mode: str, save: bool = True) -> Dict[str, Any]:
    claude_plan, claude_error = _call_claude(task)
    gemini_plan, gemini_error = _call_gemini(task)
    consensus = _build_consensus(task, claude_plan, gemini_plan)
    timestamp = _now_iso()
    network_probe: Optional[Dict[str, Any]] = None

    if _NETCHECK_ENABLED and not claude_plan and not gemini_plan:
        network_probe = _network_probe()

    runtime = _build_runtime_meta(
        task=task,
        timestamp=timestamp,
        consensus=consensus,
        claude_ok=bool(claude_plan),
        gemini_ok=bool(gemini_plan),
        claude_error=claude_error,
        gemini_error=gemini_error,
    )
    if network_probe is not None:
        runtime["network_probe"] = network_probe

        if not network_probe.get("any_tcp_ok", False):
            net_risk = "Model endpoint network probe failed (DNS/TCP). 네트워크/방화벽 점검 필요."
            risks = consensus.get("risks", [])
            if isinstance(risks, list) and net_risk not in risks:
                consensus["risks"] = [net_risk, *risks][:5]

            checks = consensus.get("checks", [])
            diag_check = "python3 core/system/plan_council.py --self-check --require-both"
            if isinstance(checks, list) and diag_check not in checks:
                consensus["checks"] = [diag_check, *checks][:6]

    consensus["runtime"] = runtime

    if runtime.get("unstable"):
        unstable_risk = (
            "Plan Council 변동성 감지: timestamp/models_used/status를 확인하고 신선한 결과인지 검증 필요"
        )
        risks = consensus.get("risks", [])
        if isinstance(risks, list) and unstable_risk not in risks:
            consensus["risks"] = [unstable_risk, *risks][:5]

    payload = {
        "timestamp": timestamp,
        "mode": mode,
        "task": task,
        "claude": {"ok": bool(claude_plan), "error": claude_error, "plan": claude_plan},
        "gemini": {"ok": bool(gemini_plan), "error": gemini_error, "plan": gemini_plan},
        "consensus": consensus,
        "runtime": runtime,
    }
    if save:
        _append_report(payload)
    return payload


def _render_hook_text(payload: Dict[str, Any], max_items: int = 3) -> str:
    consensus = payload.get("consensus", {})
    status = consensus.get("status", "degraded")
    models = ", ".join(consensus.get("models_used", [])) or "none"
    intent = str(consensus.get("intent", "")).strip()
    steps = consensus.get("steps", [])[:max_items]
    risks = consensus.get("risks", [])[:max_items]
    runtime = consensus.get("runtime") if isinstance(consensus.get("runtime"), dict) else {}
    reliability_score = _safe_float(runtime.get("reliability_score"), default=-1.0)
    reliability_tier = str(runtime.get("reliability_tier", "")).strip().lower()
    gate = str(runtime.get("gate_recommendation", "")).strip().lower()
    expires_at = str(runtime.get("expires_at_utc", "")).strip()
    unstable = bool(runtime.get("unstable", False))

    if status == "degraded" and not consensus.get("models_used"):
        return (
            "━━━ PLAN COUNCIL ━━━\n"
            "status: DEGRADED (Claude/Gemini unavailable)\n"
            "action: local fallback planning only\n"
            "━━━━━━━━━━━━━━━━━━"
        )

    lines = [
        "━━━ PLAN COUNCIL ━━━",
        f"status: {status.upper()}",
        f"models: {models}",
    ]
    if reliability_score >= 0:
        tier = reliability_tier or "unknown"
        lines.append(f"reliability: {reliability_score:.2f} ({tier})")
    if gate:
        lines.append(f"gate: {gate}")
    if unstable:
        lines.append("stability: unstable")
    if expires_at:
        lines.append(f"expires: {expires_at}")
    if intent:
        lines.append(f"intent: {intent[:140]}")
    if steps:
        lines.append("steps:")
        for idx, step in enumerate(steps, start=1):
            lines.append(f"{idx}. {step}")
    if risks:
        lines.append("risks:")
        for risk in risks:
            lines.append(f"- {risk}")
    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def _has_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def self_check(require_both: bool = False) -> int:
    issues: List[str] = []

    if not _has_module("google.genai"):
        issues.append("missing python module: google.genai")
    if not _has_module("anthropic"):
        issues.append("missing python module: anthropic")

    has_gemini_key = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
    has_claude_key = bool(os.getenv("ANTHROPIC_API_KEY"))

    if require_both:
        if not has_gemini_key:
            issues.append("missing key: GOOGLE_API_KEY or GEMINI_API_KEY")
        if not has_claude_key:
            issues.append("missing key: ANTHROPIC_API_KEY")
    else:
        if not has_gemini_key and not has_claude_key:
            issues.append("missing keys: no model key configured")

    if issues:
        for issue in issues:
            print(f"BLOCKED {issue}")
        print("BLOCKED")
        return 1

    print("READY")
    return 0


def _exit_code(payload: Dict[str, Any]) -> int:
    """Exit code contract:
    0 = ready + go          → 구현 진행 가능
    2 = needs_clarification → 범위 불명확. 사용자 확인 후 진행.
    3 = degraded/caution    → 네트워크 오류, 단일 모델, 신뢰도 이슈. 사용자 승인 후 진행.
    (1 = 미사용. 네트워크 오류도 hard stop하지 않음)
    """
    consensus = payload.get("consensus", {})
    status = consensus.get("status", "degraded")
    decision = consensus.get("decision", "go")
    models_used = consensus.get("models_used", [])
    runtime = consensus.get("runtime") if isinstance(consensus.get("runtime"), dict) else {}
    gate = str(runtime.get("gate_recommendation", "")).strip().lower()

    if gate == "hard_stop":
        return 3  # hard_stop → caution으로 다운그레이드 (네트워크 오류 포함)
    if gate == "needs_clarification":
        return 2
    if status == "degraded" and not models_used:
        return 3  # 둘 다 실패 → caution (HARD STOP 제거)
    if status == "degraded":
        return 3  # 한 모델만 성공
    if decision == "needs_clarification":
        return 2  # 범위 불명확
    if gate == "caution":
        return 3  # 신뢰도/변동성 주의
    return 0  # ready + go


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan council (Claude + Gemini)")
    parser.add_argument("--task", help="Task text for planning")
    parser.add_argument("--mode", default="manual", choices=["manual", "preflight", "hook"])
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    parser.add_argument("--no-save", action="store_true", help="Do not append report")
    parser.add_argument("--max-items", type=int, default=3, help="max steps/risks in hook text")
    parser.add_argument("--self-check", action="store_true", help="validate runtime prerequisites")
    parser.add_argument("--require-both", action="store_true", help="require both Claude+Gemini availability")
    args = parser.parse_args()

    _load_env_defaults()

    if args.self_check:
        return self_check(require_both=args.require_both)

    if not args.task:
        print("ERROR --task is required (or use --self-check)")
        return 1

    payload = run_council(task=args.task, mode=args.mode, save=not args.no_save)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
        return _exit_code(payload)

    if args.mode == "hook":
        print(_render_hook_text(payload, max_items=max(1, args.max_items)))
        return _exit_code(payload)

    consensus = payload.get("consensus", {})
    runtime = consensus.get("runtime") if isinstance(consensus.get("runtime"), dict) else {}
    print(f"status: {consensus.get('status')}")
    print(f"models: {', '.join(consensus.get('models_used', [])) or 'none'}")
    if runtime:
        print(
            "runtime: "
            f"reliability={runtime.get('reliability_score')} "
            f"tier={runtime.get('reliability_tier')} "
            f"gate={runtime.get('gate_recommendation')}"
        )
        net = runtime.get("network_probe")
        if isinstance(net, dict):
            print(
                "network: "
                f"all_dns_ok={net.get('all_dns_ok')} "
                f"any_tcp_ok={net.get('any_tcp_ok')}"
            )
        print(
            "stamp: "
            f"timestamp={runtime.get('status_stamp', {}).get('timestamp', '')} "
            f"expires={runtime.get('expires_at_utc', '')}"
        )
    print(f"intent: {consensus.get('intent', '')}")
    print("steps:")
    for idx, step in enumerate(consensus.get("steps", []), start=1):
        print(f"{idx}. {step}")
    print("risks:")
    for risk in consensus.get("risks", []):
        print(f"- {risk}")
    print("checks:")
    for check in consensus.get("checks", []):
        print(f"- {check}")
    return _exit_code(payload)


if __name__ == "__main__":
    raise SystemExit(main())
