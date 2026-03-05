#!/usr/bin/env python3
"""
Corpus Manager — LAYER OS 지식 풀 관리자

역할:
  1. SA 분석 결과 → corpus/entries/ 저장
  2. 테마별 군집 인덱스(corpus/index.json) 갱신
  3. Gardener가 군집 성숙도 판단에 사용

설계 원칙:
  - 신호 1개 즉시 발행이 아닌, 축적 후 군집 단위 발행
  - Magazine B 방식: 충분히 익은 주제만 에세이화
  - 임계점: 동일 테마 5개 이상 + 최소 72시간 분포
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent


class CorpusManager:
    """
    지식 풀 관리자.
    SA 분석 결과를 누적하고 Gardener의 군집 탐지를 지원한다.
    """

    # 군집 성숙 임계점
    CLUSTER_MIN_ENTRIES = 3       # 동일 테마 최소 entry 수 (5→3: 초기 corpus 대응)
    CLUSTER_MIN_HOURS = 72        # first_seen 이후 경과 시간 (72h = 3일 숙성)
    CLUSTER_MIN_SOURCES = 1       # 최소 소스 다양성 (단일 소스 허용 — 멀티소스 corpus 구축 전)

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.corpus_dir = project_root / "knowledge" / "corpus"
        self.entries_dir = self.corpus_dir / "entries"
        self.index_path = self.corpus_dir / "index.json"

        self.corpus_dir.mkdir(parents=True, exist_ok=True)
        self.entries_dir.mkdir(parents=True, exist_ok=True)

        if not self.index_path.exists():
            self._init_index()

    def _init_index(self):
        index = {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "last_updated": None,
            "clusters": {},
            "publish_queue": [],
            "published": []
        }
        self.index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2))

    def _load_index(self) -> Dict:
        try:
            return json.loads(self.index_path.read_text())
        except Exception:
            self._init_index()
            return json.loads(self.index_path.read_text())

    def _save_index(self, index: Dict):
        index["last_updated"] = datetime.now().isoformat()
        self.index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2))

    def add_entry(self, signal_id: str, sa_analysis: Dict, signal_data: Dict) -> str:
        """
        SA 분석 완료 후 호출. corpus entry 저장 + 인덱스 갱신.

        Args:
            signal_id: 원본 신호 ID
            sa_analysis: SA가 반환한 분석 결과
            signal_data: 원본 신호 데이터

        Returns:
            entry_id
        """
        entry_id = f"entry_{signal_id}"
        entry_path = self.entries_dir / f"{entry_id}.json"

        # 이미 존재하면 스킵
        if entry_path.exists():
            logger.info("[Corpus] 이미 존재: %s", entry_id)
            return entry_id

        # 테마 추출 (SA 분석에서)
        themes = sa_analysis.get("themes", [])
        category = sa_analysis.get("category", "미분류")
        strategic_score = sa_analysis.get("strategic_score", 0)
        summary = sa_analysis.get("summary", "")
        key_insights = sa_analysis.get("key_insights", [])
        source_path = str(signal_data.get("signal_path") or signal_data.get("source_path") or "").strip()
        if not source_path:
            source_path = f"knowledge/signals/{signal_id}.json"

        # Entry 구조
        entry = {
            "entry_id": entry_id,
            "signal_id": signal_id,
            "signal_type": signal_data.get("type", "text_insight"),
            "captured_at": signal_data.get("captured_at", ""),
            "indexed_at": datetime.now().isoformat(),
            "category": category,
            "themes": themes,
            "strategic_score": strategic_score,
            "summary": summary,
            "key_insights": key_insights,
            "raw_content_preview": str(signal_data.get("content", ""))[:300],
            "source_path": source_path,
            "used_in_essay": None,  # 에세이 발행 시 issue ID 기록
        }

        entry_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2))
        logger.info("[Corpus] Entry 추가: %s | 카테고리: %s | 테마: %s", entry_id, category, themes[:2])

        # 인덱스 갱신
        self._update_index(entry)

        return entry_id

    def _update_index(self, entry: Dict):
        """테마별 군집 인덱스에 entry 추가"""
        index = self._load_index()

        themes = entry.get("themes", [entry.get("category", "미분류")])[:2]  # 군집 과분화 방지: entry당 최대 2개
        for theme in themes:
            if theme not in index["clusters"]:
                index["clusters"][theme] = {
                    "theme": theme,
                    "entry_ids": [],
                    "first_seen": entry["indexed_at"],
                    "last_seen": entry["indexed_at"],
                    "maturity": "accumulating",  # accumulating → ripe → published
                    "essay_issued": None,
                }

            cluster = index["clusters"][theme]
            if entry["entry_id"] not in cluster["entry_ids"]:
                cluster["entry_ids"].append(entry["entry_id"])
            cluster["last_seen"] = entry["indexed_at"]

        self._save_index(index)

    def get_ripe_clusters(self) -> List[Dict]:
        """
        성숙한 군집 반환. Gardener가 호출해서 에세이 트리거 판단에 사용.

        성숙 조건:
          - entry 5개 이상
          - 최초~최후 entry 간격 72시간 이상
          - 소스 타입 2종 이상
          - 아직 발행되지 않은 것 (essay_issued == None)
        """
        index = self._load_index()
        ripe = []

        for theme, cluster in index["clusters"].items():
            if cluster.get("essay_issued"):
                continue
            if cluster.get("maturity") == "published":
                continue

            entry_ids = cluster.get("entry_ids", [])
            if len(entry_ids) < self.CLUSTER_MIN_ENTRIES:
                continue

            # 시간 숙성 확인 (first_seen 이후 경과 시간 기준)
            # 버그 수정: entries 간 간격이 아닌, 클러스터가 시스템에 존재한 기간으로 측정
            entries = self._load_entries(entry_ids)
            source_types = set()
            for e in entries:
                source_types.add(e.get("signal_type", "text_insight"))

            try:
                first_seen = datetime.fromisoformat(cluster["first_seen"][:19])
                hours_since_first = (datetime.now() - first_seen).total_seconds() / 3600
            except Exception:
                hours_since_first = 0

            if hours_since_first < self.CLUSTER_MIN_HOURS:
                continue

            hours_span = hours_since_first  # 리포트용

            if len(source_types) < self.CLUSTER_MIN_SOURCES:
                # 소스 다양성 조건은 경고만, 차단하지 않음 (유연성)
                logger.debug("[Corpus] %s: 소스 단일 타입이나 진행", theme)

            avg_score = sum(e.get("strategic_score", 0) for e in entries) / len(entries)

            ripe.append({
                "theme": theme,
                "entry_count": len(entry_ids),
                "entry_ids": entry_ids,
                "hours_span": round(hours_span, 1),
                "source_types": list(source_types),
                "avg_strategic_score": round(avg_score, 1),
                "first_seen": cluster["first_seen"],
                "last_seen": cluster["last_seen"],
            })

        # 점수 높은 것 우선
        ripe.sort(key=lambda x: x["avg_strategic_score"], reverse=True)
        return ripe

    def _load_entries(self, entry_ids: List[str]) -> List[Dict]:
        entries = []
        for eid in entry_ids:
            path = self.entries_dir / f"{eid}.json"
            if path.exists():
                try:
                    entries.append(json.loads(path.read_text()))
                except Exception:
                    pass
        return entries

    def get_entries_for_essay(self, entry_ids: List[str]) -> List[Dict]:
        """에세이 작성용 entry 전체 내용 반환 (CE Agent가 RAG용으로 호출)"""
        return self._load_entries(entry_ids)

    def mark_cluster_published(self, theme: str, issue_id: str):
        """에세이 발행 완료 시 군집 상태 업데이트"""
        index = self._load_index()

        if theme in index["clusters"]:
            cluster = index["clusters"][theme]
            cluster["maturity"] = "published"
            cluster["essay_issued"] = issue_id

            # 해당 entry들도 마킹
            for eid in cluster.get("entry_ids", []):
                path = self.entries_dir / f"{eid}.json"
                if path.exists():
                    try:
                        entry = json.loads(path.read_text())
                        entry["used_in_essay"] = issue_id
                        path.write_text(json.dumps(entry, ensure_ascii=False, indent=2))
                    except Exception:
                        pass

            # publish_queue에서 제거, published에 추가
            index["publish_queue"] = [
                q for q in index["publish_queue"] if q.get("theme") != theme
            ]
            index["published"].append({
                "theme": theme,
                "issue_id": issue_id,
                "published_at": datetime.now().isoformat(),
                "entry_count": len(cluster.get("entry_ids", [])),
            })

        self._save_index(index)
        logger.info("[Corpus] 군집 발행 완료: %s → %s", theme, issue_id)

    def get_summary(self) -> Dict:
        """현재 corpus 상태 요약 (QUANTA 갱신용)"""
        index = self._load_index()
        clusters = index.get("clusters", {})

        total_entries = sum(len(c.get("entry_ids", [])) for c in clusters.values())
        ripe = self.get_ripe_clusters()

        return {
            "total_entries": total_entries,
            "total_clusters": len(clusters),
            "ripe_clusters": len(ripe),
            "published_count": len(index.get("published", [])),
            "ripe_themes": [r["theme"] for r in ripe[:3]],
            "last_updated": index.get("last_updated"),
        }
