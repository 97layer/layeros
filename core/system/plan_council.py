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
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_FILE = PROJECT_ROOT / "knowledge" / "system" / "plan_council_reports.jsonl"

DEFAULT_GEMINI_MODEL = os.getenv("PLAN_COUNCIL_GEMINI_MODEL", "gemini-2.5-flash")
DEFAULT_CLAUDE_MODEL = os.getenv("PLAN_COUNCIL_CLAUDE_MODEL", "claude-sonnet-4-5")


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
        return None, f"gemini call failed: {exc}"


def _call_claude(task: str) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        import anthropic
    except Exception as exc:  # noqa: BLE001
        return None, f"claude import failed: {exc}"

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None, "claude key missing"

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
        return None, f"claude call failed: {exc}"


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
    if not sources:
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

    payload = {
        "timestamp": _now_iso(),
        "mode": mode,
        "task": task,
        "claude": {"ok": bool(claude_plan), "error": claude_error, "plan": claude_plan},
        "gemini": {"ok": bool(gemini_plan), "error": gemini_error, "plan": gemini_plan},
        "consensus": consensus,
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
    1 = degraded (둘 다)    → HARD STOP. 네트워크/키 오류. 구현 금지.
    2 = needs_clarification → 범위 불명확. 사용자 확인 후 진행.
    3 = degraded (한 모델)  → 단일 모델. 리스크 명시 후 진행 여부 판단.
    """
    consensus = payload.get("consensus", {})
    status = consensus.get("status", "degraded")
    decision = consensus.get("decision", "go")
    models_used = consensus.get("models_used", [])

    if status == "degraded" and not models_used:
        return 1  # 둘 다 실패
    if status == "degraded":
        return 3  # 한 모델만 성공
    if decision == "needs_clarification":
        return 2  # 범위 불명확
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
    print(f"status: {consensus.get('status')}")
    print(f"models: {', '.join(consensus.get('models_used', [])) or 'none'}")
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
