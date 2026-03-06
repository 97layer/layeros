#!/usr/bin/env python3
"""
LAYER OS — Token Efficiency Report
기존 JSONL 로그에서 토큰/비용 효율 지표를 계산하여 출력.
스키마 변경 없음 — 읽기 전용.

Usage:
  python3 core/scripts/efficiency_report.py
  python3 core/scripts/efficiency_report.py --json
  python3 core/scripts/efficiency_report.py --last N   # 최근 N건 기준
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ── 파일 경로 ──────────────────────────────────────────────
DISPATCH_LOG   = PROJECT_ROOT / "knowledge/system/plan_dispatch_metrics.jsonl"
COUNCIL_LOG    = PROJECT_ROOT / "knowledge/system/plan_council_reports.jsonl"
DOCTOR_LOG     = PROJECT_ROOT / "knowledge/system/harness_doctor_reports.jsonl"
PENDING_LOG    = PROJECT_ROOT / "knowledge/system/plan_dispatch_pending.jsonl"


def _load_jsonl(path: Path, last: int = 0) -> List[Dict]:
    if not path.exists():
        return []
    lines = [json.loads(l) for l in path.read_text().strip().splitlines() if l.strip()]
    return lines[-last:] if last > 0 else lines


# ── 1. Plan Dispatch 효율 ──────────────────────────────────
def dispatch_efficiency(last: int = 0) -> Dict[str, Any]:
    rows = _load_jsonl(DISPATCH_LOG, last)
    if not rows:
        return {}

    total      = len(rows)
    fallbacks  = sum(1 for r in rows if r.get("fallback"))
    smoke      = sum(1 for r in rows if r.get("reason") == "smoke_mode"
                     or r.get("phase") == "smoke")
    executed   = sum(1 for r in rows if r.get("executed"))
    complexity = Counter(r.get("complexity", "unknown") for r in rows)

    # smoke = Gemini API 미호출 → 절약된 full-council 비율
    smoke_save_pct   = round(smoke / total * 100, 1)
    fallback_pct     = round(fallbacks / total * 100, 1)
    execution_pct    = round(executed / total * 100, 1)

    return {
        "total": total,
        "executed": executed,
        "execution_rate_pct": execution_pct,
        "fallback_count": fallbacks,
        "fallback_rate_pct": fallback_pct,
        "smoke_count": smoke,
        "smoke_save_pct": smoke_save_pct,       # Gemini 호출 절약 비율
        "full_council_count": total - smoke,
        "complexity": dict(complexity),
        # 효율 판정: fallback < 10% AND smoke > 40% = 양호
        "grade": _grade_dispatch(fallback_pct, smoke_save_pct),
    }


def _grade_dispatch(fallback_pct: float, smoke_pct: float) -> str:
    if fallback_pct > 15:
        return "poor"
    if fallback_pct > 8 or smoke_pct < 30:
        return "fair"
    return "good"


# ── 2. Plan Council 효율 ──────────────────────────────────
def council_efficiency(last: int = 0) -> Dict[str, Any]:
    rows = _load_jsonl(COUNCIL_LOG, last)
    if not rows:
        return {}

    total = len(rows)
    statuses  = Counter(r.get("consensus", {}).get("status", "")  for r in rows)
    decisions = Counter(r.get("consensus", {}).get("decision", "") for r in rows)

    ready         = statuses.get("ready", 0)
    degraded      = statuses.get("degraded", 0)
    degraded_lite = statuses.get("degraded-lite", 0)
    go            = decisions.get("go", 0)
    clarify       = decisions.get("needs_clarification", 0)

    # effective hit rate: ready일 때만 Claude+Gemini 양쪽 토큰 사용
    # degraded = 1개 모델만 소비 (절반)
    # effective_cost = ready*2 + (degraded+lite)*1  (상대 단위)
    effective_cost   = ready * 2 + (degraded + degraded_lite) * 1
    max_cost         = total * 2
    cost_efficiency  = round((max_cost - effective_cost) / max_cost * 100, 1)

    # clarification 중 실제 재시도된 비율 추정
    # (pending 로그에서 동일 task_hash 2회 이상 = 재시도)
    pending_rows = _load_jsonl(PENDING_LOG)
    hash_counts  = Counter(r.get("task_hash", "") for r in pending_rows)
    retried      = sum(1 for c in hash_counts.values() if c >= 2)
    retry_rate_pct = round(retried / clarify * 100, 1) if clarify > 0 else 0.0

    return {
        "total": total,
        "ready_count": ready,
        "ready_rate_pct": round(ready / total * 100, 1),
        "degraded_count": degraded + degraded_lite,
        "degraded_rate_pct": round((degraded + degraded_lite) / total * 100, 1),
        "go_count": go,
        "go_rate_pct": round(go / total * 100, 1),
        "clarification_count": clarify,
        "clarification_rate_pct": round(clarify / total * 100, 1),
        "clarification_retried": retried,
        "clarification_retry_rate_pct": retry_rate_pct,   # 재시도된 건
        "clarification_dead_pct": round(100 - retry_rate_pct, 1),  # 버려진 건
        "wasted_council_calls_pct": round((degraded + degraded_lite) / total * 100, 1),
        "cost_efficiency_pct": cost_efficiency,   # 낮을수록 낭비 많음
        "grade": _grade_council(ready / total, (degraded + degraded_lite) / total),
    }


def _grade_council(ready_rate: float, degraded_rate: float) -> str:
    if ready_rate >= 0.5:
        return "good"
    if ready_rate >= 0.2 or degraded_rate < 0.7:
        return "fair"
    return "poor"          # 대부분 degraded = API 연결 문제


# ── 3. Harness Doctor 추세 ─────────────────────────────────
def doctor_trend(last: int = 10) -> Dict[str, Any]:
    rows = _load_jsonl(DOCTOR_LOG)
    if not rows:
        return {}

    recent = rows[-last:]
    scores = [r.get("score", 0) for r in recent]
    avg    = round(sum(scores) / len(scores), 1) if scores else 0
    trend  = scores[-1] - scores[0] if len(scores) >= 2 else 0

    fail_checks: Counter = Counter()
    for r in recent:
        for c in r.get("checks", []):
            if c.get("status") == "fail":
                fail_checks[c["name"]] += 1

    return {
        "window": last,
        "avg_score": avg,
        "latest_score": scores[-1] if scores else 0,
        "trend_delta": trend,        # 양수 = 개선, 음수 = 악화
        "score_history": scores,
        "recurring_fails": dict(fail_checks.most_common(5)),
    }


# ── 4. 종합 효율 점수 (0~100) ─────────────────────────────
def composite_score(disp: Dict, cncl: Dict, doc: Dict) -> Dict[str, Any]:
    """
    각 지표를 정규화하여 단일 효율 점수 산출.
    가중치: 시스템 안정성(doctor) 40 + 낭비 방지(council) 35 + 실행 정확도(dispatch) 25
    """
    # doctor: 0~100 점수를 그대로
    doc_score = doc.get("latest_score", 0) if doc else 0

    # council: 낭비 없을수록 높음
    # - ready_rate(30) + (1-degraded_rate)(30) + go_rate(20) + retry_of_clarify(20)
    if cncl:
        rr = cncl.get("ready_rate_pct", 0) / 100
        dr = 1 - cncl.get("degraded_rate_pct", 100) / 100
        gr = cncl.get("go_rate_pct", 0) / 100
        rt = cncl.get("clarification_retry_rate_pct", 0) / 100
        council_score = (rr * 30 + dr * 30 + gr * 20 + rt * 20)
    else:
        council_score = 0

    # dispatch: fallback 낮고 smoke 높고 실행률 높을수록 좋음
    if disp:
        fb  = 1 - min(disp.get("fallback_rate_pct", 0) / 20, 1.0)   # 20%+ = 0
        sm  = min(disp.get("smoke_save_pct", 0) / 60, 1.0)           # 60%+ = 만점
        ex  = disp.get("execution_rate_pct", 0) / 100
        dispatch_score = (fb * 40 + sm * 30 + ex * 30)
    else:
        dispatch_score = 0

    composite = round(doc_score * 0.40 + council_score * 0.35 + dispatch_score * 0.25, 1)

    grade = "excellent" if composite >= 85 else \
            "good"      if composite >= 70 else \
            "fair"      if composite >= 55 else "poor"

    return {
        "composite": composite,
        "grade": grade,
        "breakdown": {
            "doctor_40": round(doc_score * 0.40, 1),
            "council_35": round(council_score * 0.35, 1),
            "dispatch_25": round(dispatch_score * 0.25, 1),
        },
    }


# ── 출력 ──────────────────────────────────────────────────
def print_report(last: int = 0) -> Dict[str, Any]:
    disp  = dispatch_efficiency(last)
    cncl  = council_efficiency(last)
    doc   = doctor_trend(10)
    comp  = composite_score(disp, cncl, doc)

    grade_icon = {"excellent": "🟢", "good": "🟡", "fair": "🟠", "poor": "🔴"}

    def g(d: dict, key: str, fmt: str = "") -> str:
        v = d.get(key, "—")
        if fmt == "pct" and isinstance(v, (int, float)):
            return f"{v:.1f}%"
        if fmt == "int" and isinstance(v, (int, float)):
            return str(int(v))
        return str(v)

    icon = grade_icon.get(comp.get("grade", "poor"), "❓")

    lines = [
        "",
        "══════════════════════════════════════════════",
        f"  LAYER OS  Token Efficiency Report",
        f"  {icon} 종합 효율 점수: {comp['composite']:.1f}/100  [{comp['grade'].upper()}]",
        "══════════════════════════════════════════════",
        "",
        "┌─ Plan Dispatch ──────────────────────────────",
        f"│  총 요청:          {g(disp,'total','int')}건",
        f"│  실행률:           {g(disp,'execution_rate_pct','pct')}",
        f"│  폴백률:           {g(disp,'fallback_rate_pct','pct')}  ← 낮을수록 좋음",
        f"│  smoke 절약률:     {g(disp,'smoke_save_pct','pct')}  ← 높을수록 Gemini 호출 절약",
        f"│  복잡도:           {disp.get('complexity',{})}",
        f"│  등급:             {g(disp,'grade')}",
        "│",
        "├─ Plan Council ───────────────────────────────",
        f"│  총 호출:          {g(cncl,'total','int')}건",
        f"│  ready(양쪽 성공): {g(cncl,'ready_rate_pct','pct')}  ({g(cncl,'ready_count','int')}건)",
        f"│  degraded(낭비):   {g(cncl,'wasted_council_calls_pct','pct')}  ({g(cncl,'degraded_count','int')}건) ← API 연결 실패",
        f"│  go 승인률:        {g(cncl,'go_rate_pct','pct')}",
        f"│  clarification:    {g(cncl,'clarification_rate_pct','pct')}  ({g(cncl,'clarification_count','int')}건)",
        f"│    └ 재시도됨:     {g(cncl,'clarification_retry_rate_pct','pct')}  ({g(cncl,'clarification_retried','int')}건)",
        f"│    └ dead(버려짐): {g(cncl,'clarification_dead_pct','pct')}  ← 이 비율만큼 낭비",
        f"│  비용 효율:        {g(cncl,'cost_efficiency_pct','pct')}  ← 높을수록 토큰 절약",
        f"│  등급:             {g(cncl,'grade')}",
        "│",
        "├─ Harness Doctor (최근 10회) ─────────────────",
        f"│  평균 점수:        {g(doc,'avg_score')}",
        f"│  최신 점수:        {g(doc,'latest_score')}",
        f"│  추세:             {'+' if doc.get('trend_delta',0)>=0 else ''}{doc.get('trend_delta',0)} (양수=개선)",
        f"│  점수 이력:        {' → '.join(str(s) for s in doc.get('score_history',[])[-8:])}",
    ]

    recurring = doc.get("recurring_fails", {})
    if recurring:
        lines.append(f"│  반복 실패 항목:   {list(recurring.keys())}")

    lines += [
        "│",
        "├─ 종합 점수 분해 ──────────────────────────────",
        f"│  Doctor    (40%): {comp['breakdown']['doctor_40']:.1f}점",
        f"│  Council   (35%): {comp['breakdown']['council_35']:.1f}점",
        f"│  Dispatch  (25%): {comp['breakdown']['dispatch_25']:.1f}점",
        f"│  합계:            {comp['composite']:.1f}/100",
        "│",
        "└─ 개선 권고 ───────────────────────────────────",
    ]

    # 자동 권고
    issues = []
    if cncl.get("wasted_council_calls_pct", 0) > 50:
        issues.append("  ⚠ Council degraded > 50% → 네트워크 허용 환경에서만 full council 호출 권장")
    if cncl.get("clarification_dead_pct", 0) > 60:
        issues.append("  ⚠ clarification dead > 60% → needs_clarification 트리거 기준 강화 필요")
    if disp.get("fallback_rate_pct", 0) > 10:
        issues.append("  ⚠ 폴백률 > 10% → plan_dispatch 라우팅 정확도 점검 필요")
    if disp.get("smoke_save_pct", 0) < 30:
        issues.append("  ⚠ smoke 비율 낮음 → simple 작업에도 full council 호출 중")
    if doc.get("trend_delta", 0) < -5:
        issues.append("  ⚠ 시스템 점수 하락 추세 → harness_doctor 실패 항목 점검")

    if not issues:
        issues.append("  ✅ 특이 사항 없음")

    lines += issues
    lines.append("══════════════════════════════════════════════")
    lines.append("")

    print("\n".join(lines))

    return {
        "dispatch": disp,
        "council":  cncl,
        "doctor":   doc,
        "composite": comp,
    }


# ── CLI ───────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="LAYER OS Token Efficiency Report")
    parser.add_argument("--json",   action="store_true", help="JSON 출력")
    parser.add_argument("--last",   type=int, default=0, help="최근 N건만 집계 (0=전체)")
    args = parser.parse_args()

    data = print_report(args.last)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
