#!/usr/bin/env python3
"""
Weekly Rollup Generator — LAYER OS

매주 월요일 실행 (또는 수동).
지난 7일의 signals + corpus + essays + growth를 .md 롤업으로 생성.

출력: knowledge/reports/weekly_pattern_md
"""

import json
import logging
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
KNOWLEDGE = PROJECT_ROOT / "knowledge"

logger = logging.getLogger(__name__)


# ── 데이터 수집 ──────────────────────────────────

def _count_signals(days: int = 7) -> Dict:
    """지난 N일 신호 통계"""
    cutoff = datetime.now() - timedelta(days=days)
    signals_dir = KNOWLEDGE / "signals"
    total = 0
    by_type: Counter = Counter()

    if not signals_dir.exists():
        return {"total": 0, "by_type": {}}

    for sf in signals_dir.glob("**/*.json"):
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            captured = data.get("captured_at", "")
            if captured:
                dt = datetime.fromisoformat(captured[:19])
                if dt < cutoff:
                    continue
            total += 1
            by_type[data.get("type", "unknown")] += 1
        except Exception:
            pass

    return {"total": total, "by_type": dict(by_type)}


def _collect_corpus(days: int = 7) -> Dict:
    """지난 N일 corpus 분석 통계"""
    cutoff = datetime.now() - timedelta(days=days)
    entries_dir = KNOWLEDGE / "corpus" / "entries"
    scores: List[float] = []
    themes: Counter = Counter()
    categories: Counter = Counter()
    analyzed = 0

    if not entries_dir.exists():
        return {"analyzed": 0, "avg_score": 0, "themes": [], "categories": {}}

    for ef in entries_dir.glob("*.json"):
        try:
            entry = json.loads(ef.read_text(encoding="utf-8"))
            indexed = entry.get("indexed_at", "")
            if indexed:
                dt = datetime.fromisoformat(indexed[:19])
                if dt < cutoff:
                    continue
            analyzed += 1
            score = entry.get("strategic_score", 0)
            if score:
                scores.append(score)
            for t in entry.get("themes", []):
                themes[t] += 1
            cat = entry.get("category", "")
            if cat:
                categories[cat] += 1
        except Exception:
            pass

    top_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:8]
    avg = round(sum(scores) / len(scores), 1) if scores else 0

    return {
        "analyzed": analyzed,
        "avg_score": avg,
        "themes": top_themes,
        "categories": dict(categories),
    }


def _count_essays(days: int = 7) -> int:
    """지난 N일 발행 에세이 수 (archive/ 디렉토리 기준)"""
    cutoff = datetime.now() - timedelta(days=days)
    archive_dir = PROJECT_ROOT / "website" / "archive"
    count = 0

    if not archive_dir.exists():
        return 0

    for idx in archive_dir.glob("essay-*/index.html"):
        try:
            mtime = datetime.fromtimestamp(idx.stat().st_mtime)
            if mtime >= cutoff:
                count += 1
        except Exception:
            pass

    return count


def _load_growth() -> Dict:
    """현재 월 growth 데이터"""
    month_str = datetime.now().strftime("%Y%m")
    path = KNOWLEDGE / "reports" / "growth" / f"growth_{month_str}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


# ── 롤업 생성 ──────────────────────────────────

def _week_id() -> str:
    """ISO 주차 문자열: YYYYWNN"""
    now = datetime.now()
    year, week, _ = now.isocalendar()
    return f"{year}W{week:02d}"


def _period_range(days: int = 7) -> tuple:
    """(시작일, 종료일) 문자열"""
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def generate_rollup(days: int = 7) -> Path:
    """주간 롤업 .md 생성"""
    week = _week_id()
    start, end = _period_range(days)

    signals = _count_signals(days)
    corpus = _collect_corpus(days)
    essays = _count_essays(days)
    growth = _load_growth()

    # ── frontmatter + 본문 조립
    lines = [
        "---",
        f"type: weekly-rollup",
        f"period: {start} ~ {end}",
        f"week: {week}",
        f"created: {datetime.now().strftime('%Y-%m-%d')}",
        f"status: raw",
        "tags: [주간롤업]",
        "---",
        "",
        f"# 주간 롤업 — {week}",
        f"> {start} ~ {end}",
        "",
        "## 신호 유입",
        f"- 수집: **{signals['total']}**건",
    ]

    if signals["by_type"]:
        for stype, cnt in signals["by_type"].items():
            lines.append(f"  - {stype}: {cnt}")

    lines += [
        "",
        "## Corpus 분석",
        f"- SA 분석 완료: **{corpus['analyzed']}**건",
        f"- 평균 전략점수: **{corpus['avg_score']}**",
    ]

    if corpus["themes"]:
        lines.append("- 부상 테마:")
        for theme, cnt in corpus["themes"]:
            lines.append(f"  - {theme} ({cnt}회)")

    if corpus["categories"]:
        lines.append("- 카테고리 분포:")
        for cat, cnt in corpus["categories"].items():
            lines.append(f"  - {cat}: {cnt}")

    lines += [
        "",
        "## 에세이 발행",
        f"- 이번 주 발행: **{essays}**편",
    ]

    # growth 섹션
    if growth:
        content = growth.get("content", {})
        lines += [
            "",
            "## 성장 지표 (월간 누적)",
            f"- 에세이 누적: {content.get('essays_published', '-')}",
            f"- 신호 누적: {content.get('signals_captured', '-')}",
            f"- ripe 군집: {content.get('clusters_ripe', '-')}",
        ]

    lines += ["", f"---", f"*Generated: {datetime.now().isoformat(timespec='minutes')}*", ""]

    # 저장
    out_path = KNOWLEDGE / "reports" / f"weekly_{week}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("주간 롤업 생성: %s", out_path)
    return out_path


# ── CLI ──────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    path = generate_rollup(days)
    print(f"✅ {path}")
