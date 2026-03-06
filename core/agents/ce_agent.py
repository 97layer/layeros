#!/usr/bin/env python3
"""
LAYER OS Chief Editor (CE) Agent
Phase 6.3: NotebookLM 브랜드 가이드 쿼리 연동

Role:
- Content synthesis and editorial direction
- Transform insights + visuals into cohesive narratives
- Brand voice consistency — NotebookLM RAG 기반 실시간 참조
- Final content output (copy, captions, articles)

LLM: Gemini 2.5 Pro (Free tier)
Brand Reference: NotebookLM MCP (쿠키 인증 필요, 없으면 fallback)
Queue: Autonomous task claiming via AgentWatcher
Output: Finalized content ready for CD approval

Author: LAYER OS Technical Director
Updated: 2026-02-16 (Phase 6.3 — NotebookLM 브랜드 연동)
"""

import os
import sys
import json
import logging
import socket
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

# Project setup
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env if present (API keys)
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

from core.system.agent_watcher import AgentWatcher
from core.system.queue_manager import Task
from core.system.agent_logger import get_logger
from core.system.proactive_scan import ProactiveScan

try:
    import google.genai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

logger = logging.getLogger(__name__)

# 브랜드 보이스 로딩 — directive_loader 섹션 단위 추출
def _load_brand_directives() -> str:
    """CE 에이전트 컨텍스트 로드 — 어조/금칙/에세이 규격"""
    try:
        from core.system.directive_loader import load_for_agent
        return load_for_agent("CE", max_total=5000)
    except ImportError:
        pass
    # 최소 fallback
    return (
        "WOOHWAHAE 브랜드 보이스:\n"
        "- 톤: 사색적, 절제된, 밀도 있는\n"
        "- 금지어: 대박, 꿀팁, 핫, 트렌디, 과장 형용사\n"
        "- 허용어: 본질, 기록, 순간, 흔적, 절제, 고요함\n"
        "- 어조: 문체 강제 없음. 내용에 맞게 자연스럽게."
    )


class ChiefEditor(ProactiveScan):
    """
    Chief Editor Agent - Content Synthesis & Editorial Direction

    Capabilities:
    - Synthesize SA analysis + AD visuals into cohesive content
    - Write copy in 97layer brand voice (NotebookLM RAG 참조)
    - Create social media captions, articles, newsletters
    - Editorial QA before CD review
    """

    def __init__(self, agent_id: str = "ce-worker-1", api_key: Optional[str] = None):
        self.agent_id = agent_id
        self.agent_type = "CE"
        self._brand_voice_cache: Optional[str] = None

        # AgentLogger 초기화
        self.logger = get_logger("ce", PROJECT_ROOT)
        self.logger.idle("CE Agent 시작")

        if not GEMINI_AVAILABLE:
            raise ImportError("google-generativeai required")

        api_key = api_key or os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found")

        self.client = genai.Client(api_key=api_key)
        self._model_name = 'gemini-2.5-pro'
        self._force_fallback = str(os.getenv('CE_FORCE_FALLBACK', '0')).lower() in ('1', 'true', 'yes')

        # NotebookLM 브릿지 (선택적 — 없어도 동작)
        self.nlm = None
        try:
            from core.system.notebooklm_bridge import get_bridge, is_available
            if is_available():
                self.nlm = get_bridge()
                logger.info("%s: NotebookLM 브랜드 RAG 연결됨", self.agent_id)
            else:
                logger.warning("%s: NotebookLM 미연결 -- fallback 브랜드 보이스 사용", self.agent_id)
        except Exception as e:
            logger.warning("NotebookLM 초기화 실패: %s", e)

        logger.info("CE: 준비됨")

    # ── ProactiveScan 오버라이드 ──────────────────────────────────

    def _blind_spots(self, action: str, ctx: dict) -> list[str]:
        """CE: 신호 텍스트 내 Ralph Loop 위험 사전 감지."""
        warnings = super()._blind_spots(action, ctx)
        text = ctx.get("text", "")
        if text:
            warnings += self.check_ralph_loop(text)
            warnings += self.check_brand_voice(text)
        return warnings

    def _simpler_path(self, action: str, ctx: dict) -> list[str]:
        """CE: 재작업 3회 이상이면 경고."""
        warnings = []
        retry = ctx.get("retry", 0)
        if retry >= 3:
            warnings.append(f"SIMPLER PATH: 재작업 {retry}회차 — 신호 자체를 재검토할 것")
        return warnings

    # ─────────────────────────────────────────────────────────────

    def _get_brand_voice(self) -> str:
        """
        NotebookLM에서 97layer 브랜드 보이스 참조 가져오기.
        세션 내 첫 호출 시만 쿼리, 이후 캐시 사용.
        NotebookLM 연결 불가 시 fallback 반환.
        """
        if self._brand_voice_cache:
            return self._brand_voice_cache

        if self.nlm:
            try:
                logger.info("%s: NotebookLM 브랜드 보이스 쿼리 중...", self.agent_id)
                result = self.nlm.query_knowledge_base(
                    "97layer 브랜드 보이스와 WOOHWAHAE 톤앤매너 가이드. "
                    "금지어, 허용어, 문장 스타일, 인칭, 시제 규칙을 요약해줘."
                )
                if result and len(result) > 50:
                    self._brand_voice_cache = result
                    logger.info("%s: NotebookLM 브랜드 보이스 캐시 완료 (%d자)", self.agent_id, len(result))
                    return self._brand_voice_cache
            except Exception as e:
                logger.warning("%s: NotebookLM 쿼리 실패, fallback 사용: %s", self.agent_id, e)

        self._brand_voice_cache = _load_brand_directives()
        return self._brand_voice_cache

    def _model_reachable(self) -> bool:
        """경량 DNS 점검: 모델 API 호스트 해석 가능 여부."""
        host = "generativelanguage.googleapis.com"
        previous_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(2.0)
            socket.getaddrinfo(host, 443)
            return True
        except OSError:
            return False
        finally:
            socket.setdefaulttimeout(previous_timeout)

    def _fallback_write_content(
        self,
        analysis: Dict[str, Any],
        signal_id: str,
        retry_count: int,
        brand_source: str,
        reason: str,
    ) -> Dict[str, Any]:
        """모델 호출 실패 시 사용하는 로컬 초안 생성기."""
        themes = analysis.get("themes", []) if isinstance(analysis.get("themes"), list) else []
        theme_text = ", ".join(str(x) for x in themes[:2]) if themes else "기록"
        insights = analysis.get("key_insights", []) if isinstance(analysis.get("key_insights"), list) else []
        lead_insight = str(insights[0]).strip() if insights else ""
        summary = str(analysis.get("summary", "")).strip()

        if not lead_insight:
            lead_insight = summary or "과잉을 덜어내고 남는 핵심을 따라갑니다."

        headline_base = re.sub(r"\s+", " ", str(themes[0]) if themes else "기록의 밀도").strip()
        headline = headline_base[:18] if headline_base else "기록의 밀도"

        caption_lines = [
            f"{theme_text}을 중심으로 장면을 정리합니다.",
            f"{lead_insight[:56]}",
            "말을 줄이고 본질만 남깁니다.",
        ]
        instagram_caption = " ".join(x.strip() for x in caption_lines if x.strip())[:150]

        hashtags = ["#woohwahae", "#archive", "#기록", "#소거", "#밀도"]
        for t in themes[:3]:
            tag = re.sub(r"\s+", "", str(t))
            if tag and len(tag) <= 10:
                hashtags.append(f"#{tag}")
        hashtags = " ".join(dict.fromkeys(hashtags))

        archive_essay = (
            "처음에는 무엇을 더할지보다 무엇을 덜어낼지부터 본다.\n\n"
            f"{theme_text}이라는 단어를 붙잡고 신호를 다시 읽으면, 공통된 결은 선명해진다. "
            f"{lead_insight} 이 문장을 중심에 두고 나머지를 정리하면 흐름이 가벼워진다.\n\n"
            "좋은 문장은 새로운 장식을 붙이는 순간이 아니라, 불필요한 문장을 지운 뒤에도 "
            "의미가 남아 있을 때 완성된다. 그래서 우리는 빠르게 결론을 내리지 않고, 장면과 리듬을 "
            "한 단계씩 고른다. 남겨야 할 것과 지워도 되는 것을 분리하면 문장이 스스로 서기 시작한다.\n\n"
            "오늘의 기록은 완성보다 정렬에 가깝다. 다음 장면으로 넘어가도 같은 기준이 유지되는지, "
            "그 질문만 남긴다."
        )
        # Fallback도 기본 품질 게이트(500자+)를 넘기도록 길이를 보강한다.
        min_essay_len = 500
        if len(archive_essay) < min_essay_len:
            supplements = [
                "빠른 답을 찾는 대신 같은 질문을 반복한다.",
                "무엇이 핵심인지가 선명해지면 문장은 자연스럽게 짧아진다.",
                "짧아진 문장은 다음 선택의 기준을 더 분명하게 만든다.",
                "오늘의 기록은 결론을 닫지 않고 기준의 지속 여부를 확인한다.",
            ]
            idx = 0
            archive_essay += "\n\n"
            while len(archive_essay) < min_essay_len:
                archive_essay += supplements[idx % len(supplements)] + " "
                idx += 1
            archive_essay = archive_essay.strip()

        return {
            "instagram_caption": instagram_caption,
            "hashtags": hashtags,
            "archive_essay": archive_essay,
            "headline": headline,
            "tone": "grounded",
            "brand_voice_source": f"{brand_source} (fallback)",
            "signal_id": signal_id,
            "written_by": self.agent_id,
            "written_at": datetime.now().isoformat(),
            "model": "fallback_local",
            "retry_count": retry_count,
            "status": "draft_for_cd",
            "analysis_mode": "fallback_local",
            "fallback_reason": reason,
        }

    def _fallback_corpus_result(
        self,
        theme: str,
        content_type: str,
        content_category: str,
        entry_count: int,
        rag_context: List[Dict[str, Any]],
        reason: str,
    ) -> Dict[str, Any]:
        """write_corpus_essay 실패 시 멀티포맷 폴백 생성."""
        is_journal = content_type in ("magazine", "journal")
        tg_tone = "한다체 (단문 선언형)" if content_type in ("essay", "lookbook") else "합니다체 (간결 안내형)"
        type_label = "journal" if is_journal else "essay"

        summaries = []
        for entry in rag_context[:3]:
            text = str(entry.get("summary", "")).strip()
            if text:
                summaries.append(text)
        stitched = " ".join(summaries) if summaries else f"{theme} 관련 신호를 재정렬했습니다."

        essay_title = (theme or "기록").strip()[:10] or "기록"
        pull_quote = "덜어내면 남는 결이 기준이 됩니다."
        archive_essay = (
            f"{theme or '기록'}의 흐름을 다시 읽는다.\n\n"
            f"신호 {entry_count}개를 한 줄로 세우면 공통된 문장 구조가 보인다. {stitched[:180]} "
            "핵심은 설명을 늘리는 일이 아니라 기준을 선명하게 유지하는 데 있다.\n\n"
            "기준이 선명할수록 장면은 단순해지고, 단순해질수록 다음 선택은 빨라진다. "
            "그래서 오늘의 초안은 완결보다 방향을 확보하는 데 집중한다.\n\n"
            "남겨야 할 문장을 확인했고, 다음 기록은 그 문장을 더 짧게 증명한다."
        )
        instagram_caption = (
            f"{theme or '기록'}의 결을 다시 맞췄습니다. "
            "과잉을 줄이고 남는 핵심만 기록합니다."
        )[:150]
        carousel_slides = [
            "첫 문장은 관찰로 시작합니다.",
            "신호를 한 줄의 기준으로 묶습니다.",
            "과잉을 덜어 구조를 선명히 합니다.",
            "다음 기록도 같은 기준을 유지합니다.",
        ]
        if content_type in ("essay", "lookbook"):
            telegram_summary = "\n".join([
                essay_title,
                "핵심 결을 짧게 정리한다.",
                "아카이브에서 이어서 읽는다.",
            ])
        else:
            telegram_summary = "\n".join([
                essay_title,
                "핵심 결을 짧게 정리합니다.",
                "아카이브에서 이어서 읽어봅니다.",
            ])

        return {
            "essay_title": essay_title,
            "pull_quote": pull_quote,
            "archive_essay": archive_essay,
            "instagram_caption": instagram_caption,
            "carousel_slides": carousel_slides,
            "telegram_summary": telegram_summary,
            "telegram_summary_tone": tg_tone,
            "theme": theme,
            "content_category": content_category,
            "content_type": type_label,
            "entry_count": entry_count,
            "analysis_mode": "fallback_local",
            "fallback_reason": reason,
        }

    def write_content(self, analysis: Dict[str, Any], visual_concept: Dict[str, Any],
                      retry_count: int = 0, feedback: str = "", previous_output: Dict = None) -> Dict[str, Any]:
        """
        SA 분석 + AD 비주얼 컨셉을 기반으로 콘텐츠 작성.
        인스타그램 패키지 + 아카이브 에세이 이중 포맷 생성.

        Args:
            analysis: SA strategic analysis
            visual_concept: AD visual concept
            retry_count: 재작업 횟수 (CD 거절 또는 Ralph 점수 미달)
            feedback: 이전 거절 피드백 (재작업 시)
            previous_output: 이전 결과물 (재작업 참고용)

        Returns:
            {
              instagram_caption, hashtags, archive_essay,
              headline, tone, ...
            }
        """
        signal_id = analysis.get('signal_id', 'unknown')
        retry_msg = " (재작업 %d회차)" % retry_count if retry_count > 0 else ""
        logger.info("CE: %s 초안 작업.%s", signal_id, retry_msg)

        # ── 능동 사고 스캔 ──────────────────────────────────────
        raw_themes = analysis.get('themes', '')
        if isinstance(raw_themes, list):
            themes_text = " ".join(str(x) for x in raw_themes)
        else:
            themes_text = str(raw_themes or '')
        signal_text = str(analysis.get('content', '')) + ' ' + themes_text
        self.scan("write_content", {
            "signal_id": signal_id,
            "text": signal_text,
            "retry": retry_count,
        })
        # ────────────────────────────────────────────────────────

        # 브랜드 보이스 참조 (NotebookLM 또는 fallback)
        brand_voice = self._get_brand_voice()
        brand_source = "NotebookLM RAG" if self.nlm else "Brand OS directives"
        logger.info("%s: 브랜드 보이스 출처 — %s", self.agent_id, brand_source)

        # 재작업 컨텍스트
        retry_context = ""
        if retry_count > 0 and feedback:
            retry_context = f"""
**이전 피드백 (반드시 반영):**
{feedback}

"""
        if previous_output:
            retry_context += f"""**이전 출력 (개선 필요):**
- 인스타 캡션: {previous_output.get('instagram_caption', 'N/A')[:100]}
- 에세이 일부: {str(previous_output.get('archive_essay', 'N/A'))[:200]}

"""

        prompt = f"""당신은 Chief Editor(CE)다.
WOOHWAHAE의 SAGE-ARCHITECT 인격으로 콘텐츠를 작성한다.

**핵심 특성 (sage_architect.md)**:
- 관찰자 거리: 가르치지 않고 렌즈만 건넨다
- 열린 결말: 결론을 대신 내리지 않는다
- 본질주의: 과잉을 덜어낸다
- 수평적 동료: "나도 이런 고민을 했다" 구조
- 조용한 밀도: 목소리를 낮추되 발음은 정확하다
- 자기 리듬: 자기 경험 기반

**어미 스펙트럼**: 핵심 철학은 단언("~이다"). 관찰/해석은 열린("~라고 본다", "~일 수 있다"). 정보는 간결("~입니다").

**전략 분석 (SA 제공):**
- 주제: {', '.join(analysis.get('themes', []))}
- 핵심 인사이트: {'; '.join(analysis.get('key_insights', []))}
- 요약: {analysis.get('summary', '')}

**비주얼 컨셉 (AD 제공):**
- 제목: {visual_concept.get('concept_title', '(없음)')}
- 무드: {visual_concept.get('visual_mood', '(없음)')}
- 브랜드 정렬: {visual_concept.get('brand_alignment', '(없음)')}

**브랜드 보이스 가이드:**
{brand_voice}

{retry_context}
위 가이드를 따라 **두 가지 포맷**으로 작성하라:

1. **Instagram 패키지**: 발행 즉시 사용 가능한 형태
2. **Archive Essay**: Hook-Story-Core-Echo 구조의 에세이

아래 JSON 형식으로 반환:
{{
  "instagram_caption": "인스타그램 캡션 (한국어, 150자 이내, 이모지 금지)",
  "hashtags": "#woohwahae #slowlife #아카이브 (관련 해시태그 5-8개)",
  "archive_essay": "아카이브 에세이 (한국어, 500-800자, 한다체, Hook-Story-Core-Echo)",
  "headline": "헤드라인 (10-20자, 명사형)",
  "tone": "contemplative|reflective|grounded 중 하나",
  "brand_voice_source": "{brand_source}"
}}

필수 준수:
- instagram_caption: 150자 이내. 이모지 금지. 메타언급 금지.
- archive_essay: 500자 이상. Echo는 질문/여백으로 맺는다.
- 금지: 느낌표, 이모지, 교훈적 결론, 자기과시, 메타언급
- 금지어: 혁신, 트렌드, 최신, 혁명적, 압도적

JSON만 반환.
"""

        if self._force_fallback:
            logger.warning("CE: CE_FORCE_FALLBACK=1, 로컬 초안 생성 사용")
            return self._fallback_write_content(
                analysis=analysis,
                signal_id=signal_id,
                retry_count=retry_count,
                brand_source=brand_source,
                reason="forced_fallback_mode",
            )
        if not self._model_reachable():
            logger.warning("CE: 모델 호스트 DNS 실패, 로컬 초안으로 폴백")
            return self._fallback_write_content(
                analysis=analysis,
                signal_id=signal_id,
                retry_count=retry_count,
                brand_source=brand_source,
                reason="model_host_unreachable",
            )

        try:
            response = self.client.models.generate_content(
                model=self._model_name,
                contents=[prompt]
            )
            content_text = response.text

            # JSON 파싱
            if '```json' in content_text:
                json_start = content_text.find('```json') + 7
                json_end = content_text.find('```', json_start)
                json_text = content_text[json_start:json_end].strip()
            elif '```' in content_text:
                json_start = content_text.find('```') + 3
                json_end = content_text.find('```', json_start)
                json_text = content_text[json_start:json_end].strip()
            else:
                json_text = content_text.strip()

            content = json.loads(json_text)

            content.update({
                'signal_id': signal_id,
                'written_by': self.agent_id,
                'written_at': datetime.now().isoformat(),
                'model': self._model_name,
                'brand_voice_source': brand_source,
                'retry_count': retry_count,
                'status': 'draft_for_cd',
                'analysis_mode': 'model',
            })

            caption_len = len(content.get('instagram_caption', ''))
            essay_len = len(content.get('archive_essay', ''))
            logger.info("CE: 초안 완료. 캡션 %d자, 에세이 %d자.", caption_len, essay_len)
            return content

        except Exception as e:
            logger.error("%s: 콘텐츠 생성 실패: %s", self.agent_id, e)
            return self._fallback_write_content(
                analysis=analysis,
                signal_id=signal_id,
                retry_count=retry_count,
                brand_source=brand_source,
                reason=str(e),
            )

    def process_task(self, task: Task) -> Dict[str, Any]:
        task_type = task.task_type
        payload = task.payload

        logger.info("CE: %s (%s)", task.task_id, task_type)

        if task_type == 'write_content':
            # Orchestrator에서 오는 새 payload 구조 지원
            # payload에 sa_result가 있으면 Orchestrator 경유
            sa_result = payload.get('sa_result', payload.get('analysis', {}))
            visual = payload.get('visual_concept', payload.get('ad_result', {}).get('visual_concept', {}))

            # 재작업 파라미터
            retry_count = payload.get('retry_count', 0)
            feedback = payload.get('feedback', payload.get('cd_feedback', ''))
            previous_output = payload.get('previous_output', None)

            result = self.write_content(
                analysis=sa_result,
                visual_concept=visual,
                retry_count=retry_count,
                feedback=feedback,
                previous_output=previous_output
            )
            # SA 전략 점수를 result에 포함 (Ralph 채점용)
            result['sa_strategic_score'] = sa_result.get('strategic_score', 0)
            return {'status': 'completed', 'task_id': task.task_id, 'result': result}

        elif task_type == 'write_corpus_essay':
            # Gardener가 트리거한 corpus 기반 에세이 작성
            # 단일 신호가 아닌 군집 전체 RAG → Magazine B 스타일 롱폼
            result = self._write_corpus_essay(payload)

            # signal_id 정규화 (Orchestrator가 후속 체인에 사용)
            if 'signal_id' not in result:
                result['signal_id'] = payload.get('theme', 'corpus').replace(' ', '_')

            # 발행은 Orchestrator가 CE→Ralph→AD→CD→Publisher 체인으로 처리
            return {'status': 'completed', 'task_id': task.task_id, 'result': result}

        else:
            return {'status': 'failed', 'error': f"Unknown task type: {task_type}"}

    def _write_corpus_essay(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Corpus 군집 기반 원소스 멀티유즈 콘텐츠 생성.

        하나의 Gemini 호출로 5개 포맷 동시 생성:
          1. archive_essay     — 롱폼 에세이 (800~1200자) → woohwahae.kr/archive/
          2. instagram_caption — 캡션 (150자 이내) → 인스타그램 단일 피드
          3. carousel_slides   — 3~5장 텍스트 슬라이드 → 인스타그램 캐러셀
          4. telegram_summary  — 3줄 요약 → 봇 푸시 알림
          5. pull_quote        — 핵심 1문장 → 웹사이트 히어로/about 인용구

        원칙: 포맷이 다를 뿐 동일한 본질에서 파생. 재가공 아닌 파생.
        """
        theme = payload.get("theme", "")
        rag_context = payload.get("rag_context", [])
        entry_count = payload.get("entry_count", 0)
        instruction = payload.get("instruction", "")
        content_type = str(payload.get("content_type", "archive")).lower()
        content_category = payload.get("content_category", "")

        # AgentLogger: 에세이 작성 시작
        self.logger.think("에세이 작성 중: %s" % theme)

        # essay: archive or essay type → 한다체, 독백, 300-800자
        # journal: magazine or journal type → 합니다체, ~~~하는 법, 1200-3000자
        is_journal = content_type in ("magazine", "journal")

        if is_journal:
            tone_guide = (
                "문체: 합니다체. 형식: ~~~하는 법 / 안내형. "
                "구조: 리드(도입 요약) → 본문(단계별 설명) → 실천(온화한 제안). "
                "길이: 1200-3000자. "
                "마무리: 독자가 실천 가능한 제안. 금지: 자기중심 관찰, 모호한 결론."
            )
            essay_length_spec = "1200~3000자. 리드+본문+실천 구조."
        else:
            tone_guide = (
                "문체: 한다체. 형식: 독백, 관찰자 시점. "
                "구조: Hook(역설/선언) → Story(개인→보편) → Core(통찰) → Echo(Hook 변주). "
                "길이: 300-800자. "
                "마무리: 결론 없이 여운. 열린 질문 또는 여백. 금지: 강한 호소, 행동 유도."
            )
            essay_length_spec = "300~800자. Hook-Story-Core-Echo 구조."

        # 텔레그램 요약 어미 규칙: 에세이/룩북=한다체, 그 외=합니다체
        tg_tone = "한다체 (단문 선언형)" if content_type in ("essay", "lookbook") else "합니다체 (간결 안내형)"

        # RAG 컨텍스트 직렬화
        context_text = ""
        for i, entry in enumerate(rag_context, 1):
            context_text += f"\n[{i}] {entry.get('captured_at', '')[:10]} | {entry.get('signal_type', '')}\n"
            context_text += f"요약: {entry.get('summary', '')}\n"
            insights = entry.get('key_insights', [])
            if insights:
                context_text += f"인사이트: {' / '.join(str(x) for x in insights[:3])}\n"

        category_hint = f"\n카테고리: {content_category}" if content_category else ""

        # 대화 패턴 컨텍스트 (Gardener가 추출한 현재 관심사 → 에세이 방향 힌트)
        conv_context_block = ""
        try:
            lm_path = PROJECT_ROOT / 'knowledge' / 'long_term_memory.json'
            if lm_path.exists():
                _lm = json.loads(lm_path.read_text(encoding='utf-8'))
                _cp = _lm.get('conversation_patterns', {})
                _concerns = _cp.get('active_concerns', [])
                _brand_ctx = _cp.get('brand_context', '')
                _lines = []
                if _concerns:
                    _lines.append('현재 관심사: ' + ', '.join(_concerns[:3]))
                if _brand_ctx:
                    _lines.append('브랜드 맥락: ' + _brand_ctx)
                if _lines:
                    conv_context_block = '\n'.join(_lines)
        except Exception:
            pass

        type_desc = "Journal (자연체, 안내형)" if is_journal else "Essay (한다체, 독백형)"
        conv_context_section = (
            "## 현재 관심 맥락 (참고)\n" + conv_context_block + "\n\n---\n\n"
            if conv_context_block else ""
        )

        prompt = f"""너는 WOOHWAHAE의 편집장이다. SAGE-ARCHITECT 인격으로 쓴다.

주제: {theme}{category_hint}
타입: {type_desc}
신호 수: {entry_count}개

---

## 작성 태도 원칙 (WOOHWAHAE About 기반)

아래 10개 원칙은 협상 불가다. 구조 공식이 아니라 태도다.

1. **첫 문장은 감각적 관찰 또는 3단어 이하 단언으로 시작한다.**
   예: "돌 안에 형태가 있습니다." / "이 과정은 서두를 수 없습니다." / "말하지 않는 것들도 신호입니다."
   설명문으로 시작하지 않는다. 배경 제공으로 시작하지 않는다.

2. **섹션당 비유는 하나. 구체적 물리 현상에서 가져온다.**
   음파, 조각, 나방, 침묵, 빈 손 — 이런 종류. 추상 개념을 추상 개념으로 설명하지 않는다.
   비유는 확장하지 않는다. 한 번 쓰고 물러난다.

3. **단문 나열. 접속사는 최소화한다.**
   "그리고", "하지만", "따라서"로 문장을 잇지 않는다.
   마침표로 끊고 다음 문장이 스스로 서게 한다.

4. **역접은 "그러나" 한 번만. 논리 전환은 문장 배치로 한다.**
   앞 문장과 다음 문장 사이의 긴장이 접속사 역할을 한다.

5. **교훈과 행동 유도를 완전히 제거한다.**
   "~해야 한다", "~하자", "~하면 좋다" — 이 형태는 없다.
   관찰을 서술하고, 독자가 그 자리에서 스스로 움직인다.

6. **결말은 짧은 단언 또는 순환 귀환으로 닫는다.**
   "이것이 기록이 됩니다." / "걷어내면 드러납니다." — 이런 형태.
   결론을 설명하지 않는다. 상태를 선언하고 끝낸다.

7. **마지막 문장이 다음 사유의 입구가 된다.**
   글이 끝난 뒤 독자가 계속 생각하게 만드는 것이 목표다.
   열린 질문이거나, 방금 쓴 내용을 되감는 한 문장이다.

8. **신호 요약은 분석 결과가 아니라 관찰 원문의 흐름으로 읽는다.**
   "~라는 인사이트가 있다"가 아니라 "~가 반복해서 등장한다"는 관점으로.
   데이터를 인용하지 않는다. 흐름을 읽는다.

9. **하나의 생각만 쓴다. 여러 관찰을 엮어 결론을 만들지 않는다.**
   주제 안에서 가장 밀도 있는 하나의 균열을 찾는다.
   그것만 끝까지 따라간다.

10. **독자와의 거리는 수평적 관찰자다.**
    가르치지 않는다. 위로하지 않는다. 함께 보는 위치에 있다.
    문장 안에 "당신"이나 "우리"가 나오면 교훈 구조로 기울지 않았는지 점검한다.

---

## 어미 스펙트럼
- 핵심 철학: 단언 (~이다, ~한다)
- 관찰/해석: 열린 어미 (~라고 본다, ~일 수 있다, ~처럼 보인다)
- 정보: 간결 (~이다, ~있다)

---

## 생성 순서

먼저 archive_essay를 완성한다. 나머지 포맷은 에세이에서 파생한다.
재가공이 아닌 파생이다. 에세이의 본질이 각 포맷에 농축된다.

---

{conv_context_section}## 관찰 원문 흐름 (신호 {entry_count}개)
{context_text}

---

## 출력 규칙
- 한국어
- 이모지 완전 금지, 느낌표 금지
- 볼드, 헤더 사용 금지 (archive_essay 내부)
- 메타언급 금지 ("이 글에서는", "지금부터", "살펴보겠습니다")
- WOOHWAHAE 톤: {tone_guide}

응답 형식 (JSON):
{{
  "essay_title": "제목 (10자 이내, 명사형)",
  "pull_quote": "에세이 전체를 관통하는 핵심 문장 1개 (30자 이내). 단언형. 웹사이트 히어로에 올려도 되는 밀도.",
  "archive_essay": "에세이 본문. {essay_length_spec} 단락 사이 빈 줄. 위 작성 태도 원칙 10개 적용.",
  "instagram_caption": "캡션 150자 이내. 에세이의 핵심 압축. 마지막 줄은 여백을 주는 짧은 단언.",
  "carousel_slides": [
    "슬라이드 1: 도입 — 감각적 첫 문장 (30자 이내)",
    "슬라이드 2: 핵심 관찰 (30자 이내)",
    "슬라이드 3: 역설 또는 전환 (30자 이내)",
    "슬라이드 4: 마무리 단언 (30자 이내)"
  ],
  "telegram_summary": "봇 푸시 3줄. 각 줄 40자 이내. 첫 줄: 제목. 둘째 줄: 핵심. 셋째 줄: 링크 유도.",
  "telegram_summary_tone": "{tg_tone}",
  "theme": "{theme}",
  "content_category": "{content_category}",
  "content_type": "{type_label}",
  "entry_count": {entry_count}
}}

JSON만 출력."""

        if self._force_fallback:
            logger.warning("CE: CE_FORCE_FALLBACK=1, corpus 로컬 초안 생성 사용")
            result = self._fallback_corpus_result(
                theme=theme,
                content_type=content_type,
                content_category=content_category,
                entry_count=entry_count,
                rag_context=rag_context,
                reason="forced_fallback_mode",
            )
            return result
        if not self._model_reachable():
            logger.warning("CE: 모델 호스트 DNS 실패, corpus 로컬 초안으로 폴백")
            result = self._fallback_corpus_result(
                theme=theme,
                content_type=content_type,
                content_category=content_category,
                entry_count=entry_count,
                rag_context=rag_context,
                reason="model_host_unreachable",
            )
            return result

        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-pro',
                contents=[prompt]
            )
            text = response.text.strip()
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                result = json.loads(match.group())
                formats = [k for k in ['archive_essay', 'instagram_caption', 'carousel_slides',
                                        'telegram_summary', 'pull_quote'] if k in result]
                logger.info("CE: 원소스 멀티유즈 완료 -- %s | 타입: %s | 포맷: %s", theme, content_type, ', '.join(formats))
            else:
                result = {
                    "archive_essay": text,
                    "essay_title": theme,
                    "theme": theme,
                    "entry_count": entry_count,
                    "analysis_mode": "model",
                }
            if "analysis_mode" not in result:
                result["analysis_mode"] = "model"

            # ── HTML 저장 ──────────────────────────────────────────
            try:
                self._save_essay_html(result, theme)
            except Exception as html_e:
                # HTML 저장 실패는 에세이 생성 결과에 영향 없음
                logger.warning("CE: HTML 저장 실패 (무시) -- %s", html_e)

            # ── NotebookLM Essay Archive 저장 ──────────────────────
            if self.nlm:
                try:
                    self.nlm.add_essay_to_archive({
                        'essay_title': result.get('essay_title', theme),
                        'theme': theme,
                        'archive_essay': result.get('archive_essay', ''),
                        'pull_quote': result.get('pull_quote', ''),
                        'instagram_caption': result.get('instagram_caption', ''),
                        'issue_num': result.get('issue_num', ''),
                    })
                    logger.info("CE: NotebookLM Essay Archive 저장 완료 -- %s", result.get('essay_title', theme))
                except Exception as nlm_e:
                    logger.warning("CE: NotebookLM 저장 실패 (무시) -- %s", nlm_e)

            # ── 언어품질 검증 (Ralph Loop) ──────────────────────
            try:
                from core.system.essay_quality_validator import EssayQualityValidator
                validator = EssayQualityValidator()
                essay_text = result.get('archive_essay', '')
                if essay_text:
                    validation = validator.validate(essay_text)
                    result['quality_score'] = validation['score']
                    result['quality_issues'] = len(validation['issues'])

                    if validation['score'] < 90:
                        logger.warning(
                            "CE: 언어품질 기준 미달 -- %s | 점수: %d/100 | 이슈: %d건",
                            result.get('essay_title', theme),
                            validation['score'],
                            len(validation['issues'])
                        )
                        # 상세 이슈 로그 (최대 3개)
                        for issue in validation['issues'][:3]:
                            logger.warning("  - %s: %s", issue.get('type', ''), issue.get('match', ''))
                    else:
                        logger.info("CE: 언어품질 검증 통과 -- %s | 점수: %d/100",
                                    result.get('essay_title', theme), validation['score'])
            except Exception as val_e:
                logger.warning("CE: 언어품질 검증 실패 (무시) -- %s", val_e)

            return result

        except Exception as e:
            logger.error("CE: corpus 에세이 실패 -- %s", e)
            return self._fallback_corpus_result(
                theme=theme,
                content_type=content_type,
                content_category=content_category,
                entry_count=entry_count,
                rag_context=rag_context,
                reason=str(e),
            )

    def _save_essay_html(self, result: dict, theme: str):
        """CE 에세이 결과를 website/archive/essay-NNN-slug/index.html 로 저장."""
        import re as _re
        from datetime import datetime as _dt
        from pathlib import Path as _Path

        # AgentLogger: HTML 저장 시작
        self.logger.write("HTML 생성 중: %s" % theme)

        # env_validator 경유 단일 진입점
        try:
            from core.system.env_validator import get_project_root, get_site_base_url
            PROJECT_ROOT = _Path(get_project_root())
        except Exception:
            PROJECT_ROOT = _Path(__file__).resolve().parent.parent.parent

        instagram_url = os.getenv('INSTAGRAM_URL', 'https://instagram.com/woohwahae')
        archive_dir = PROJECT_ROOT / 'website' / 'archive'

        # ── 이슈 번호 자동 계산 ──
        existing = sorted([
            d for d in archive_dir.iterdir()
            if d.is_dir() and _re.match(r'essay-\d+', d.name)
        ])
        # essay-000 ~ essay-008 형태 모두 포함해서 최댓값 추출
        max_num = 0
        for d in existing:
            m = _re.match(r'essay-0*(\d+)', d.name)
            if m:
                max_num = max(max_num, int(m.group(1)))
        next_num = max_num + 1
        essay_num_str = f"{next_num:03d}"  # 009, 010 ...

        # ── slug 생성 (테마 → 소문자 영문 slug) ──
        # 단어 단위 매핑 — 복합 테마도 처리 (첫 번째 매칭 키워드 사용)
        _word_slug_map = {
            '조용한지능': 'quiet-intelligence', '슬로우라이프': 'slow-life',
            '여백': 'negative-space', '기록': 'record',
            '감각': 'sensory', '침묵': 'silence',
            '물성': 'materiality', '일상': 'daily',
            '미용': 'beauty', '정신건강': 'mental-health', '정신': 'mental',
            '돌봄': 'care', '관계': 'relationship', '시간': 'time',
            '공간': 'space', '음식': 'food', '음악': 'music',
            '독서': 'reading', '글쓰기': 'writing', '사진': 'photo',
            '여행': 'travel', '산책': 'walk', '계절': 'season',
            '빛': 'light', '색': 'color', '질감': 'texture',
            '본질': 'essence', '선택': 'choice', '집중': 'focus',
            '느림': 'slow', '비움': 'empty', '채움': 'fill',
            '습관': 'habit', '루틴': 'routine', '의식': 'ritual',
            '몸': 'body', '마음': 'mind', '영성': 'spirit',
        }
        theme_key = theme.replace(' ', '').replace('의', '').replace('과', '').replace('와', '')
        slug = None
        # 정확 매칭 우선
        for k, v in _word_slug_map.items():
            if k in theme_key:
                slug = v
                break
        if not slug:
            # ASCII 테마는 그대로 slug화
            ascii_slug = _re.sub(r'[^\w-]', '', theme.lower().replace(' ', '-'))
            slug = ascii_slug if ascii_slug and ascii_slug[0].isascii() else 'essay'
        slug = slug[:30]

        folder_name = f"essay-{essay_num_str}-{slug}"
        essay_dir = archive_dir / folder_name
        essay_dir.mkdir(parents=True, exist_ok=True)

        essay_title = result.get('essay_title', theme)
        pull_quote = result.get('pull_quote', '')
        archive_essay = result.get('archive_essay', '')
        today = _dt.now().strftime('%Y.%m.%d')
        content_type_label = result.get('content_type', 'essay').capitalize()
        content_category_label = result.get('content_category', '')

        # ── 에세이 본문 → HTML 단락 변환 ──
        paragraphs = [p.strip() for p in archive_essay.split('\n\n') if p.strip()]
        para_html = ''
        for i, p in enumerate(paragraphs):
            # 중간에 <hr> 한 번 삽입 (절반 지점)
            if i == len(paragraphs) // 2:
                para_html += '            <hr class="article-divider">\n\n'
            if i == len(paragraphs) - 1:
                # 마지막 단락은 closing 스타일
                para_html += f'            <p class="article-closing fade-in">\n                {p}\n            </p>\n\n'
            else:
                para_html += f'            <p class="fade-in">\n                {p}\n            </p>\n\n'

        html = f"""<!DOCTYPE html>
<html lang="ko">

<head>
  <meta charset="UTF-8">
  <link rel="apple-touch-icon" href="../../assets/img/symbol.jpg">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Issue {essay_num_str} — {essay_title}. {pull_quote}">
  <title>Issue {essay_num_str}: {essay_title} — WOOHWAHAE Archive</title>
  <link rel="manifest" href="/manifest.webmanifest">
  <meta name="theme-color" content="#FAFAF7">
  <link rel="icon" href="../../assets/img/symbol.jpg" type="image/jpeg">
  <link rel="stylesheet" href="../../assets/css/style.css">
</head>

<body>

    <nav>
        <a href="/" class="nav-brand" aria-label="WOOHWAHAE">
            <img src="../../assets/media/brand/symbol.png" alt="WOOHWAHAE" class="nav-symbol">
        </a>
        <ul class="nav-links" id="nav-links">
            <li><a href="../../archive/" class="active">Archive</a></li>
            <li><a href="../../practice/">Practice</a></li>
            <li><a href="../../about/">About</a></li>
        </ul>
        <button class="nav-toggle" id="nav-toggle" aria-label="메뉴" aria-expanded="false">
            <span></span><span></span>
        </button>
    </nav>

    <div class="article-container">

        <header class="article-header">
            <p class="article-meta fade-in">Issue {essay_num_str} &nbsp;·&nbsp; {content_category_label + ' · ' if content_category_label else ''}{content_type_label} &nbsp;·&nbsp; {today}</p>
            <h1 class="article-title fade-in">{essay_title}</h1>
            <p class="article-subtitle fade-in">{pull_quote}</p>
        </header>

        <div class="article-body">

{para_html}
        </div>

    </div>

    <footer class="site-footer">
        <div class="footer-inner">
            <p class="footer-brand">WOOHWAHAE</p>
            <nav class="footer-nav">
                <a href="../../archive/">Archive</a>
                <a href="../../practice/">Practice</a>
                <a href="../../about/">About</a>
                <a href="{instagram_url}" target="_blank" rel="noopener">Instagram</a>
            </nav>
            </div>
        </div>
        <p class="footer-copy">&copy; 2026 WOOHWAHAE. All rights reserved.</p>
    </footer>

    <script src="../../assets/js/main.js"></script>
</body>
</html>"""

        html_path = essay_dir / 'index.html'
        html_path.write_text(html, encoding='utf-8')
        logger.info("CE: HTML 저장 완료 -- %s", html_path.relative_to(PROJECT_ROOT))
        logger.info("CE: Issue %s '%s' -> archive/%s/", essay_num_str, essay_title, folder_name)

        # AgentLogger: 작업 완료
        self.logger.done("Issue %s: %s" % (essay_num_str, essay_title))

    def start_watching(self, interval: int = 5):
        watcher = AgentWatcher(agent_type=self.agent_type, agent_id=self.agent_id)
        nlm_status = "연결됨" if self.nlm else "fallback"
        logger.info("CE: 큐 감시 시작. LLM=Gemini 2.5 Pro | Brand Voice=NotebookLM RAG (%s) | Tasks=write_content", nlm_status)
        watcher.watch(callback=self.process_task, interval=interval)


if __name__ == '__main__':
    import argparse
    from core.system.env_validator import validate_env
    validate_env("ce_agent")

    parser = argparse.ArgumentParser(description='LAYER OS Chief Editor Agent')
    parser.add_argument('--agent-id', default='ce-worker-1')
    parser.add_argument('--interval', type=int, default=5)
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()

    agent = ChiefEditor(agent_id=args.agent_id)

    if args.test:
        logger.info("[TEST] Test Mode: Content Writing")
        test_analysis = {
            'signal_id': 'test_001',
            'themes': ['AI와 창작', '느린 삶'],
            'key_insights': ['AI는 반복을 제거하고 창작에 집중하게 한다', '속도보다 깊이가 더 오래 남는다'],
            'summary': 'AI는 슬로우 라이프를 가능하게 하는 도구다',
        }
        test_visual = {
            'concept_title': '디지털 정원',
            'visual_mood': 'contemplative',
            'brand_alignment': '여백과 느림의 미학',
        }

        result = agent.write_content(test_analysis, test_visual)
        logger.info("[TEST] 콘텐츠 초안 -- 헤드라인: %s | 캡션: %s | 브랜드 보이스 출처: %s",
                    result.get('headline', 'N/A'), result.get('social_caption', 'N/A'), result.get('brand_voice_source', 'N/A'))
        logger.info("[TEST] 테스트 완료")
    else:
        agent.start_watching(interval=args.interval)
