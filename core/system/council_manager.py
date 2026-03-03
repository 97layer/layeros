#!/usr/bin/env python3
"""
LAYER OS Council Manager
Gardener ripe cluster → SA/CE/AD 병렬 협의 → Telegram 승인 → CE task 생성

흐름:
    Gardener._trigger_essay_for_cluster()
        → CouncilManager.run_council(cluster)
        → SA/CE/AD 병렬 Gemini 호출
        → .infra/council/{proposal_id}.json 저장
        → council_room.md append
        → Telegram 승인/거절 버튼 발송
    Telegram callback (council_approve:id)
        → CouncilManager.approve_proposal(id)
        → CE task 생성 → 기존 파이프라인 진행
"""

import os
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
COUNCIL_PENDING_DIR = PROJECT_ROOT / ".infra" / "council"
COUNCIL_ROOM = PROJECT_ROOT / "knowledge" / "agent_hub" / ("council_room" + ".md")

# 에이전트별 협의 질문
_AGENT_QUESTIONS = {
    "SA": "전략 분석가 관점으로 이 클러스터를 평가하라. 핵심_통찰(list, 3항목), 발행_권고(YES/NO), 이유(string) 키를 가진 JSON만 반환.",
    "CE": "편집장 관점으로 이 클러스터를 평가하라. 제목_후보(list, 2항목), 방향(string, 2줄), 가능(YES/NO) 키를 가진 JSON만 반환.",
    "AD": "아트 디렉터 관점으로 이 클러스터를 평가하라. 레이아웃(string), 분위기_키워드(list, 3항목) 키를 가진 JSON만 반환.",
}
_MODEL = "gemini-2.5-flash"


class CouncilManager:
    """
    에이전트 협의 관리자.
    run_council() → 비동기 Telegram 승인 대기 (블로킹 없음)
    approve_proposal() → CE task 생성
    """

    def __init__(self):
        COUNCIL_PENDING_DIR.mkdir(parents=True, exist_ok=True)
        self._client = None

    # ─── 클라이언트 ───────────────────────────────────────────────────────────

    def _get_client(self):
        if self._client is None:
            try:
                import google.genai as genai
            except ImportError as exc:
                raise ImportError("google-generativeai 패키지 필요") from exc
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY 환경변수 없음")
            self._client = genai.Client(api_key=api_key)
        return self._client

    def _load_directive(self, agent_type: str) -> str:
        try:
            from core.system.directive_loader import load_for_agent
            return load_for_agent(agent_type, max_total=2000)
        except Exception:
            return f"당신은 LAYER OS {agent_type} 에이전트. WOOHWAHAE 슬로우라이프 브랜드 기준으로 판단."

    # ─── 에이전트 호출 ────────────────────────────────────────────────────────

    def _call_agent(self, agent_type: str, cluster: Dict) -> Dict:
        """단일 에이전트 Gemini 호출. JSON dict 반환."""
        directive = self._load_directive(agent_type)
        client = self._get_client()

        cluster_ctx = (
            f"주제: {cluster['theme']}\n"
            f"신호 수: {cluster['entry_count']}\n"
            f"전략 점수: {cluster.get('avg_strategic_score', 'N/A')}\n"
            f"시간 범위: {cluster.get('hours_span', 'N/A')}시간"
        )
        prompt = (
            f"[역할]\n{directive}\n\n"
            f"[클러스터]\n{cluster_ctx}\n\n"
            f"[질문]\n{_AGENT_QUESTIONS[agent_type]}"
        )

        try:
            response = client.models.generate_content(model=_MODEL, contents=[prompt])
            text = response.text.strip()
            if "```json" in text:
                text = text[text.find("```json") + 7 : text.find("```", text.find("```json") + 7)].strip()
            elif "```" in text:
                text = text[text.find("```") + 3 : text.find("```", text.find("```") + 3)].strip()
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": response.text[:300] if "response" in dir() else "parse error"}
        except Exception as exc:
            logger.error("[Council] %s 호출 실패: %s", agent_type, exc)
            return {"error": str(exc)}

    # ─── 메인 협의 ────────────────────────────────────────────────────────────

    def run_council(self, cluster: Dict) -> Optional[str]:
        """
        SA/CE/AD 병렬 협의 → proposal 저장 → Telegram 발송.
        블로킹 없음. CE task는 Telegram 승인 후 생성.
        Returns: proposal_id or None (GOOGLE_API_KEY 없을 때)
        """
        logger.info("[Council] 협의 시작: %s (%d개 신호)", cluster.get("theme"), cluster.get("entry_count", 0))

        try:
            views: Dict[str, Dict] = {}
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(self._call_agent, agent_type, cluster): agent_type
                    for agent_type in _AGENT_QUESTIONS
                }
                for future in as_completed(futures):
                    agent_type = futures[future]
                    try:
                        views[agent_type] = future.result()
                    except Exception as exc:
                        views[agent_type] = {"error": str(exc)}
        except (ImportError, ValueError) as exc:
            logger.warning("[Council] API 미설정, 직접 CE task 생성으로 폴백: %s", exc)
            return None

        proposal_id = str(uuid.uuid4())[:8]
        proposal = {
            "proposal_id": proposal_id,
            "created_at": datetime.now().isoformat(),
            "cluster": cluster,
            "views": views,
        }
        proposal_path = COUNCIL_PENDING_DIR / f"{proposal_id}.json"
        proposal_path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")

        self._log_to_council_room(proposal_id, cluster, views)
        self._send_telegram_proposal(proposal_id, cluster, views)

        logger.info("[Council] proposal=%s 저장 완료, Telegram 대기 중", proposal_id)
        return proposal_id

    # ─── 승인 / 거절 ──────────────────────────────────────────────────────────

    def approve_proposal(self, proposal_id: str) -> Optional[str]:
        """
        Telegram 승인 → CE task 생성.
        Returns: task_id or None
        """
        proposal_path = COUNCIL_PENDING_DIR / f"{proposal_id}.json"
        if not proposal_path.exists():
            logger.error("[Council] proposal 없음: %s", proposal_id)
            return None

        proposal = json.loads(proposal_path.read_text())
        cluster = proposal["cluster"]

        from core.system.corpus_manager import CorpusManager
        from core.system.queue_manager import QueueManager

        corpus = CorpusManager()
        entries = corpus.get_entries_for_essay(cluster.get("entry_ids", []))
        if not entries:
            logger.error("[Council] corpus entries 없음: %s", cluster.get("theme"))
            return None

        rag_context = [
            {
                "summary": e.get("summary", ""),
                "key_insights": e.get("key_insights", []),
                "themes": e.get("themes", []),
                "captured_at": e.get("captured_at", ""),
                "signal_type": e.get("signal_type", ""),
                "preview": e.get("raw_content_preview", ""),
            }
            for e in entries
        ]

        ce_view = proposal.get("views", {}).get("CE", {})
        title_hints = ce_view.get("제목_후보") or ce_view.get("title_candidates", [])

        payload = {
            "mode": "corpus_essay",
            "content_type": cluster.get("content_type", "archive"),
            "theme": cluster["theme"],
            "entry_count": cluster["entry_count"],
            "rag_context": rag_context,
            "avg_strategic_score": cluster.get("avg_strategic_score"),
            "time_span_hours": cluster.get("hours_span"),
            "council_views": proposal.get("views", {}),
            "title_hints": title_hints,
            "instruction": (
                f"주제 '{cluster['theme']}'에 관한 {cluster['entry_count']}개의 신호를 바탕으로 "
                "원소스 멀티유즈 콘텐츠를 생성하라. "
                "archive_essay(롱폼) / instagram_caption(150자) / "
                "carousel_slides(3~5장) / telegram_summary(3줄) / pull_quote(1문장) "
                "5개 포맷을 동시에. 모두 같은 본질에서 파생."
            ),
        }

        task_id = QueueManager().create_task(
            agent_type="CE",
            task_type="write_corpus_essay",
            payload=payload,
        )
        proposal_path.unlink()
        logger.info("[Council] 승인 → CE task %s (theme=%s)", task_id, cluster["theme"])

        self._append_council_room(
            f"\n- [{datetime.now().strftime('%Y-%m-%d %H:%M')}] ✅ 승인 → CE task `{task_id}` (proposal={proposal_id})\n"
        )
        return task_id

    def reject_proposal(self, proposal_id: str):
        """Telegram 거절 → proposal 삭제 + 로그."""
        proposal_path = COUNCIL_PENDING_DIR / f"{proposal_id}.json"
        if not proposal_path.exists():
            logger.warning("[Council] 거절 대상 없음: %s", proposal_id)
            return
        proposal = json.loads(proposal_path.read_text())
        theme = proposal.get("cluster", {}).get("theme", "?")
        proposal_path.unlink()
        logger.info("[Council] 거절: proposal=%s, theme=%s", proposal_id, theme)
        self._append_council_room(
            f"\n- [{datetime.now().strftime('%Y-%m-%d %H:%M')}] ❌ 거절: {theme} (proposal={proposal_id})\n"
        )

    # ─── 로깅 ─────────────────────────────────────────────────────────────────

    def _log_to_council_room(self, proposal_id: str, cluster: Dict, views: Dict):
        sa = views.get("SA", {})
        ce = views.get("CE", {})
        ad = views.get("AD", {})
        lines = [
            "\n\n---\n",
            "## [%s] Council 협의 — %s\n\n" % (datetime.now().strftime("%Y-%m-%d %H:%M"), cluster["theme"]),
            "**proposal_id**: `%s`  **신호**: %d개\n\n" % (proposal_id, cluster["entry_count"]),
            "**SA**: %s\n\n" % json.dumps(sa, ensure_ascii=False),
            "**CE**: %s\n\n" % json.dumps(ce, ensure_ascii=False),
            "**AD**: %s\n" % json.dumps(ad, ensure_ascii=False),
        ]
        self._append_council_room("".join(lines))

    def _append_council_room(self, text: str):
        try:
            with open(COUNCIL_ROOM, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception as exc:
            logger.error("[Council] council_room append 실패: %s", exc)

    # ─── Telegram 발송 (동기 requests) ────────────────────────────────────────

    def _send_telegram_proposal(self, proposal_id: str, cluster: Dict, views: Dict):
        import requests

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        admin_id = os.getenv("ADMIN_TELEGRAM_ID")
        if not bot_token or not admin_id:
            logger.warning("[Council] Telegram 환경변수 없음 — 콘솔 출력만")
            return

        def _fmt(d: Dict) -> str:
            if not isinstance(d, dict) or "error" in d:
                return str(d)[:100]
            return json.dumps(d, ensure_ascii=False)[:200]

        text = (
            "🏛️ <b>Council 협의 완료</b>\n\n"
            "📌 <b>주제</b>: %s\n"
            "📊 신호 %d개 · 점수 %s\n\n"
            "🔍 <b>SA</b>: %s\n\n"
            "✍️ <b>CE</b>: %s\n\n"
            "🎨 <b>AD</b>: %s\n\n"
            "발행할까요?"
        ) % (
            cluster["theme"],
            cluster["entry_count"],
            cluster.get("avg_strategic_score", "?"),
            _fmt(views.get("SA", {})),
            _fmt(views.get("CE", {})),
            _fmt(views.get("AD", {})),
        )

        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ 승인", "callback_data": "council_approve:%s" % proposal_id},
                {"text": "❌ 거절", "callback_data": "council_reject:%s" % proposal_id},
            ]]
        }

        try:
            resp = requests.post(
                "https://api.telegram.org/bot%s/sendMessage" % bot_token,
                json={"chat_id": admin_id, "text": text, "parse_mode": "HTML", "reply_markup": keyboard},
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.error("[Council] Telegram 발송 실패: %s", exc)
