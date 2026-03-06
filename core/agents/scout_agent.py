#!/usr/bin/env python3
"""
scout_agent.py — Brand Scout 데몬

외부 RSS/큐레이션 소스에서 신호를 자동 수집하여
기존 signal pipeline에 inject한다.

사용법:
    python core/agents/scout_agent.py --once
    python core/agents/scout_agent.py --forever
    python core/agents/scout_agent.py --forever --interval 12
"""

import argparse
import json
import logging
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

# stdlib 완료 — third-party
try:
    import feedparser
    _FEEDPARSER_AVAILABLE = True
except ImportError:
    _FEEDPARSER_AVAILABLE = False

# local
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.scripts.signal_inject import create_signal, enqueue_for_sa, save_signal
from core.scripts import signal_inject as _si
from core.system.proactive_scan import ProactiveScan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("scout_agent")

# signal_inject 모듈이 실제로 사용하는 경로를 그대로 참조한다.
# (signal_inject.PROJECT_ROOT = 97layerOS 루트, 따라서 SIGNALS_DIR = knowledge/signals/)
SIGNALS_DIR = _si.SIGNALS_DIR
SOURCES_PATH = PROJECT_ROOT / "knowledge" / "service" / "scout_sources.json"


def load_sources() -> dict:
    """scout_sources.json 로드"""
    if not SOURCES_PATH.exists():
        logger.error("소스 설정 없음: %s", SOURCES_PATH)
        return {"sources": [], "max_signals_per_source": 5}
    with open(SOURCES_PATH, encoding="utf-8") as f:
        return json.load(f)


def is_duplicate(url: str) -> bool:
    """
    knowledge/signals/ 기존 파일에서 URL 중복 체크.

    metadata.source_url 필드를 검사한다.
    파일 수가 많아지면 성능 병목이 될 수 있으나,
    현재 규모에서는 허용 가능하다.
    """
    if not SIGNALS_DIR.exists():
        return False
    for signal_file in SIGNALS_DIR.glob("*.json"):
        try:
            with open(signal_file, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("metadata", {}).get("source_url") == url:
                return True
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("신호 파일 읽기 실패 — 건너뜀: %s (%s)", signal_file.name, e)
    return False


def fetch_feed(source: dict, max_items: int = 5) -> list:
    """
    RSS 피드 파싱 후 상위 N개 항목 반환.

    Args:
        source: {"name", "url", "category", "language"}
        max_items: 반환할 최대 항목 수

    Returns:
        [{"title", "link", "summary", "published"}] 형태의 리스트.
        실패 시 빈 리스트.
    """
    if not _FEEDPARSER_AVAILABLE:
        logger.warning("feedparser 미설치 — %s 건너뜀 (pip install feedparser)", source["name"])
        return []

    url = source["url"]
    logger.info("피드 수집 시작: %s (%s)", source["name"], url)

    try:
        feed = feedparser.parse(url)
    except Exception as e:
        logger.warning("피드 파싱 예외 — %s: %s", source["name"], e)
        return []

    if feed.bozo and not feed.entries:
        logger.warning("피드 파싱 오류 — %s: %s", source["name"], feed.bozo_exception)
        return []

    items = []
    for entry in feed.entries[:max_items]:
        link = entry.get("link", "")
        if not link:
            continue
        items.append({
            "title": entry.get("title", "").strip(),
            "link": link,
            "summary": entry.get("summary", "").strip(),
            "published": entry.get("published", ""),
        })

    logger.info("피드 수집 완료 — %s: %d개 항목", source["name"], len(items))
    return items


# sage_architect.md §9 금지 어휘 — Scout 1차 소거 필터
# 제목/요약에 금지어가 1개 이상 있으면 수집하지 않는다.
_DENIED_PATTERNS = (
    "트렌드", "유행", "핫한",
    "최고", "최상", "베스트",
    "성공", "성취", "정복",
    "레벨업", "업그레이드",
    "효율", "생산성", "roi",
    "꿀팁", "노하우", "공략",
    "힐링", "치유",
    "행복", "만족", "기쁨",
    "특별한", "특별함",
)


def has_resonance(item: dict) -> bool:
    """
    sage_architect.md §9 금지어 기반 1차 소거 필터.

    제목+요약에 금지어가 포함되면 공명 불일치로 판단.
    SA가 받기 전에 걷어낸다.
    """
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    for pattern in _DENIED_PATTERNS:
        if pattern in text:
            return False
    return True


def inject_item(item: dict, source: dict) -> Optional[str]:
    """
    단일 피드 항목을 signal pipeline에 inject.

    Args:
        item: fetch_feed 반환 항목
        source: 소스 설정 dict

    Returns:
        주입된 signal_id, 또는 중복/실패/공명불일치 시 None.
    """
    url = item["link"]

    if is_duplicate(url):
        logger.debug("중복 URL 건너뜀: %s", url)
        return None

    if not has_resonance(item):
        logger.debug("공명 불일치 — 소거: %s", item["title"][:60])
        return None

    content = "%s\n\n%s" % (item["title"], item.get("summary", ""))

    signal = create_signal(
        signal_type="url_content",
        content=content,
        source_channel="crawler",
        metadata={
            "source_url": url,
            "title": item["title"],
            "crawler_source": source["name"],
            "category": source.get("category", ""),
            "language": source.get("language", ""),
            "published": item.get("published", ""),
        },
    )

    # signal_inject.generate_signal_id는 초 단위라 같은 초에 여러 항목이
    # 동일 signal_id를 가질 수 있다. uuid suffix로 충돌 방지.
    suffix = uuid.uuid4().hex[:8]
    signal["signal_id"] = "%s_%s" % (signal["signal_id"], suffix)

    try:
        save_signal(signal)
        enqueue_for_sa(signal)
    except OSError as e:
        logger.error("신호 저장 실패 — %s: %s", signal["signal_id"], e)
        return None

    logger.info("신호 주입 완료: %s | %s", signal["signal_id"], item["title"][:60])
    return signal["signal_id"]


class ScoutAgent(ProactiveScan):
    """Brand Scout 데몬 — RSS 소스 순회 및 신호 자동 수집"""

    def __init__(self):
        self.config = load_sources()
        self.sources = self.config.get("sources", [])
        self.max_per_source = self.config.get("max_signals_per_source", 5)
        self.poll_interval_hours = self.config.get("poll_interval_hours", 6)

    # ── ProactiveScan 오버라이드 ──────────────────────────────────

    def _simpler_path(self, action: str, ctx: dict) -> list[str]:
        """Scout: 소스가 없으면 실행 불필요."""
        warnings = []
        if ctx.get("source_count", 1) == 0:
            warnings.append("SIMPLER PATH: scout_sources.json에 소스 없음 — 수집 생략")
        return warnings

    # ─────────────────────────────────────────────────────────────

    def run_once(self) -> dict:
        """
        모든 소스를 한 번 순회하여 새 신호를 inject.

        Returns:
            {"injected": int, "skipped": int, "errors": int}
        """
        if not _FEEDPARSER_AVAILABLE:
            logger.error("feedparser 미설치. 실행 불가. (pip install feedparser)")
            return {"injected": 0, "skipped": 0, "errors": 1}

        # ── 능동 사고 스캔 ──────────────────────────────────────
        self.scan("run_once", {"source_count": len(self.sources)})
        # ────────────────────────────────────────────────────────

        stats = {"injected": 0, "skipped": 0, "errors": 0}
        started_at = datetime.now().isoformat()
        logger.info("Scout 실행 시작: %s | 소스 %d개", started_at, len(self.sources))

        for source in self.sources:
            try:
                items = fetch_feed(source, max_items=self.max_per_source)
            except Exception as e:
                logger.warning("소스 fetch 실패 — %s: %s", source.get("name", "?"), e)
                stats["errors"] += 1
                continue

            for item in items:
                result = inject_item(item, source)
                if result:
                    stats["injected"] += 1
                else:
                    stats["skipped"] += 1

        logger.info(
            "Scout 실행 완료 — 주입: %d, 건너뜀: %d, 오류: %d",
            stats["injected"],
            stats["skipped"],
            stats["errors"],
        )
        return stats

    def run_forever(self, interval_hours: Optional[int] = None) -> None:
        """
        주기적으로 run_once를 반복 실행.

        Args:
            interval_hours: 실행 간격 (시간). None이면 설정값 사용.
        """
        interval = interval_hours if interval_hours is not None else self.poll_interval_hours
        interval_secs = interval * 3600

        logger.info("Scout 데몬 시작 — 주기: %dh", interval)

        while True:
            self.run_once()
            next_run = datetime.fromtimestamp(time.time() + interval_secs).isoformat()
            logger.info("다음 실행 예정: %s", next_run)
            try:
                time.sleep(interval_secs)
            except KeyboardInterrupt:
                logger.info("Scout 데몬 종료 (KeyboardInterrupt)")
                break


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Brand Scout 데몬 — RSS 소스 자동 수집",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "예시:\n"
            "  python core/agents/scout_agent.py --once\n"
            "  python core/agents/scout_agent.py --forever\n"
            "  python core/agents/scout_agent.py --forever --interval 12\n"
        ),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--once",
        action="store_true",
        help="모든 소스를 한 번 순회하고 종료",
    )
    mode.add_argument(
        "--forever",
        action="store_true",
        help="주기적으로 계속 실행 (데몬 모드)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        metavar="HOURS",
        help="데몬 모드 실행 간격(시간). 기본값: scout_sources.json의 poll_interval_hours",
    )

    args = parser.parse_args()
    agent = ScoutAgent()

    if args.once:
        stats = agent.run_once()
        sys.exit(0 if stats["errors"] == 0 else 1)
    elif args.forever:
        agent.run_forever(interval_hours=args.interval)


if __name__ == "__main__":
    main()
