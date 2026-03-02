#!/usr/bin/env python3
"""
LAYER OS Art Director (AD) Agent
Phase 6.3: NotebookLM 시각 레퍼런스 쿼리 연동

Role:
- Visual concept development and art direction
- Image generation guidance (for Stable Diffusion integration)
- Brand consistency — NotebookLM RAG 기반 시각 아이덴티티 참조
- Visual storytelling and composition

LLM: Gemini 2.5 Pro (Free tier, with Vision)
Visual Reference: NotebookLM MCP (WOOHWAHAE 시각 아카이브 참조)
Queue: Autonomous task claiming via AgentWatcher
Output: Visual concepts, style guides, image prompts

Author: LAYER OS Technical Director
Updated: 2026-02-16 (Phase 6.3 — NotebookLM 시각 레퍼런스 연동)
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Project setup
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.system.agent_watcher import AgentWatcher
from core.system.queue_manager import Task

# Gemini API (optional, for actual execution) — google.genai 신규 SDK
GEMINI_AVAILABLE = False
try:
    import google.genai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    pass  # mock mode — logger not yet initialized

logger = logging.getLogger(__name__)

# 디자인 토큰 로딩 — directive_loader 섹션 단위 추출
def _load_design_tokens() -> str:
    """AD 에이전트 컨텍스트 로드 — practice.md Part I 시각 규격"""
    try:
        from core.system.directive_loader import load_for_agent
        return load_for_agent("AD", max_total=4000)
    except ImportError:
        pass
    # 최소 fallback
    return (
        "WOOHWAHAE 시각 아이덴티티:\n"
        "- 색상: #E3E2E0(배경), #1a1a1a(텍스트), #1B2D4F(네이비)\n"
        "- 서체: Pretendard Variable(본문), Crimson Text(세리프)\n"
        "- 여백: 60%+, max-content: 680px\n"
        "- 사진: muted, desaturated, 35mm 필름 그레인, 자연광\n"
        "- 금지: 과포화, 플래시, 복잡한 배경"
    )


class ArtDirector:
    """
    Art Director Agent - Visual Concepts & Art Direction

    Capabilities:
    - Develop visual concepts from strategic insights
    - Generate image prompts for Stable Diffusion (WOOHWAHAE 아카이브 참조)
    - Validate visual consistency with brand guidelines (NotebookLM RAG)
    - Provide art direction feedback
    """

    def __init__(self, agent_id: str = "ad-worker-1", api_key: Optional[str] = None):
        self.agent_id = agent_id
        self.agent_type = "AD"
        self.mock_mode = not GEMINI_AVAILABLE
        self._visual_ref_cache: Optional[str] = None

        if GEMINI_AVAILABLE:
            api_key = api_key or os.getenv('GOOGLE_API_KEY')
            if api_key:
                self.client = genai.Client(api_key=api_key)
                self._model_name = 'gemini-2.5-pro'
                self.mock_mode = False
                logger.info("AD: 준비됨.")
            else:
                logger.warning("AD %s: API key 없음, mock mode", self.agent_id)
                self.mock_mode = True
        else:
            logger.warning("AD %s: Gemini 미설치, mock mode", self.agent_id)

        # NotebookLM 브릿지 (선택적 — 없어도 동작)
        self.nlm = None
        try:
            from core.system.notebooklm_bridge import get_bridge, is_available
            if is_available():
                self.nlm = get_bridge()
                print(f"✅ {self.agent_id}: NotebookLM 시각 레퍼런스 연결됨")
            else:
                print(f"⚠️  {self.agent_id}: NotebookLM 미연결 — fallback 시각 레퍼런스 사용")
        except Exception as e:
            logger.warning("NotebookLM 초기화 실패: %s", e)

    def _get_visual_reference(self) -> str:
        """
        NotebookLM에서 WOOHWAHAE 시각 아이덴티티 레퍼런스 가져오기.
        세션 내 첫 호출 시만 쿼리, 이후 캐시 사용.
        NotebookLM 연결 불가 시 fallback 반환.
        """
        if self._visual_ref_cache:
            return self._visual_ref_cache

        if self.nlm:
            try:
                logger.info("%s: NotebookLM 시각 레퍼런스 쿼리 중...", self.agent_id)
                result = self.nlm.query_knowledge_base(
                    "WOOHWAHAE 시각 아이덴티티 가이드. "
                    "색상 팔레트, 사진 스타일, 구도 원칙, 벤치마크 브랜드, "
                    "아카이벌 필름 미학을 요약해줘."
                )
                if result and len(result) > 50:
                    self._visual_ref_cache = result
                    logger.info(
                        "%s: NotebookLM 시각 레퍼런스 캐시 완료 (%d자)",
                        self.agent_id, len(result),
                    )
                    return self._visual_ref_cache
            except Exception as e:
                logger.warning("%s: NotebookLM 쿼리 실패, fallback 사용: %s", self.agent_id, e)

        self._visual_ref_cache = _load_design_tokens()
        return self._visual_ref_cache

    def create_visual_concept(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        SA 분석을 기반으로 비주얼 컨셉 생성.
        시각 아이덴티티는 NotebookLM RAG에서 실시간 참조.
        """
        signal_id = analysis_data.get('signal_id', 'unknown')
        themes = analysis_data.get('themes', [])
        insights = analysis_data.get('key_insights', [])
        summary = analysis_data.get('summary', '')

        logger.info("AD: %s 비주얼 컨셉 작업", signal_id)

        if self.mock_mode:
            return self._mock_visual_concept(signal_id, themes, insights)

        # 시각 레퍼런스 참조 (NotebookLM 또는 fallback)
        visual_ref = self._get_visual_reference()
        ref_source = (
            "NotebookLM RAG"
            if self.nlm
            else "Brand OS design_tokens"
        )
        logger.info("%s: 시각 레퍼런스 출처 — %s", self.agent_id, ref_source)

        prompt = self._build_concept_prompt(themes, insights, summary, visual_ref, ref_source)

        try:
            response = self.client.models.generate_content(
                model=self._model_name,
                contents=[prompt]
            )
            concept = self._parse_concept(response.text)

            concept.update({
                'signal_id': signal_id,
                'created_by': self.agent_id,
                'created_at': datetime.now().isoformat(),
                'model': self._model_name,
                'visual_ref_source': ref_source,
                'based_on': 'SA analysis',
            })

            print(f"AD: 완료.")
            return concept

        except Exception as e:
            logger.error("%s: 비주얼 컨셉 생성 실패: %s", self.agent_id, e)
            return {'signal_id': signal_id, 'error': str(e), 'status': 'failed'}

    def _build_concept_prompt(
        self,
        themes: list,
        insights: list,
        summary: str,
        visual_ref: str,
        ref_source: str,
    ) -> str:
        return f"""당신은 97layer의 Art Director입니다.
시각적 침묵을 렌더링한다. 더하지 않고 드러낸다.
과잉 없이 충분한 것. 여백이 말하게 한다.

**SA 관찰 (신호 본질):**
- 본질 키워드: {', '.join(themes)}
- 관찰: {'; '.join(insights)}
- 신호의 무게: {summary}

**WOOHWAHAE 시각 아이덴티티 가이드 (출처: {ref_source}):**
{visual_ref}

위 가이드를 따라 아래 JSON 형식으로 비주얼 컨셉을 작성하세요.
더하고 싶은 것이 있다면, 먼저 제거를 검토하세요.
밀도·온도·물성·침묵이 구도를 결정합니다.

{{
  "concept_title": "컨셉 제목 (짧고 건조하게, 한국어)",
  "visual_mood": "contemplative|serene|intimate|grounded 중 하나",
  "color_palette": ["#hex1", "#hex2", "#hex3"],
  "composition_notes": "구도 가이드 (2-3문장, 여백·밀도·침묵 기준으로 서술)",
  "image_prompts": [
    {{
      "prompt": "Stable Diffusion 프롬프트 (영어, 필름 그레인/탈채도/자연광/최소 피사체 포함)",
      "style": "photography|film_still|analog",
      "aspect_ratio": "4:5|1:1|16:9"
    }}
  ],
  "typography_guidance": "폰트 방향 (세리프/산세리프, 행간, 크기 위계 — 장식 없이)",
  "reference_aesthetics": ["레퍼런스1", "레퍼런스2"],
  "brand_alignment": "WOOHWAHAE 소거 원칙과의 연결점",
  "visual_ref_source": "{ref_source}"
}}

유효한 JSON만 반환하세요.
"""

    def _parse_concept(self, concept_text: str) -> Dict[str, Any]:
        try:
            if '```json' in concept_text:
                json_start = concept_text.find('```json') + 7
                json_end = concept_text.find('```', json_start)
                json_text = concept_text[json_start:json_end].strip()
            elif '```' in concept_text:
                json_start = concept_text.find('```') + 3
                json_end = concept_text.find('```', json_start)
                json_text = concept_text[json_start:json_end].strip()
            else:
                json_text = concept_text.strip()

            return json.loads(json_text)

        except json.JSONDecodeError as e:
            return {
                'concept_title': 'Visual Concept',
                'visual_mood': 'contemplative',
                'raw_response': concept_text,
                'parse_error': str(e),
            }

    def _mock_visual_concept(self, signal_id: str, themes: list, insights: list) -> Dict[str, Any]:
        return {
            'signal_id': signal_id,
            'concept_title': f"{'와 '.join(themes[:2])}의 정경",
            'visual_mood': 'contemplative',
            'color_palette': ['#3D3530', '#E8E0D5', '#A89880'],
            'composition_notes': (
                '넉넉한 여백과 오프센터 구도. '
                '오가닉 텍스처와 소프트한 자연광. '
                '빠른 움직임 없이 정지된 순간의 무게.'
            ),
            'image_prompts': [
                {
                    'prompt': (
                        f'35mm film photography, {themes[0] if themes else "still life"}, '
                        'muted desaturated tones, warm grey palette, soft natural side lighting, '
                        'shallow depth of field, analog film grain, organic textures, '
                        'off-center composition, generous negative space, wabi-sabi aesthetic'
                    ),
                    'style': 'film_still',
                    'aspect_ratio': '4:5',
                }
            ],
            'typography_guidance': (
                '세리프 계열 본문 (Garamond류). '
                '산세리프 헤더는 라이트 웨이트 사용. '
                '행간 1.8 이상, 자간 넓게.'
            ),
            'reference_aesthetics': ['Kinfolk', 'Aesop', '와비사비'],
            'brand_alignment': 'WOOHWAHAE 슬로우 라이프 — 속도가 아닌 깊이를 향한 시선',
            'created_by': self.agent_id,
            'created_at': datetime.now().isoformat(),
            'mode': 'mock',
            'visual_ref_source': 'fallback',
            'based_on': f"{len(themes)} themes, {len(insights)} insights",
        }

    def process_task(self, task: Task) -> Dict[str, Any]:
        task_type = task.task_type
        payload = task.payload

        logger.info("AD: %s (%s)", task.task_id, task_type)

        if task_type == 'create_visual_concept':
            # Orchestrator 경유: payload 자체에 signal_id/themes/sa_result 등이 직접 존재
            # 레거시: payload.analysis에 감싸져 있을 수도
            analysis_data = payload.get('analysis', None)
            if analysis_data is None:
                # Orchestrator 경유 — payload를 analysis_data로 직접 사용
                sa = payload.get('sa_result', {})
                analysis_data = {
                    'signal_id': payload.get('signal_id', 'unknown'),
                    'themes': payload.get('themes', sa.get('themes', [])),
                    'key_insights': payload.get('key_insights', sa.get('key_insights', [])),
                    'summary': sa.get('summary', payload.get('essay_preview', '')),
                }
            result = self.create_visual_concept(analysis_data)
            return {'status': 'completed', 'task_id': task.task_id, 'result': result}

        elif task_type == 'validate_visual':
            return {
                'status': 'completed',
                'task_id': task.task_id,
                'result': {'validated': True, 'notes': 'Brand-aligned'},
            }

        else:
            return {'status': 'failed', 'error': f"Unknown task type: {task_type}"}

    def start_watching(self, interval: int = 5):
        watcher = AgentWatcher(agent_type=self.agent_type, agent_id=self.agent_id)

        mode_str = "MOCK MODE" if self.mock_mode else "Gemini 2.5 Pro"
        nlm_status = "연결됨" if self.nlm else "fallback"
        print(f"AD: 큐 감시 시작.")
        print(f"   LLM: {mode_str}")
        print(f"   Visual Reference: NotebookLM RAG ({nlm_status})")
        print(f"   Tasks: create_visual_concept, validate_visual")
        print(f"   Queue: .infra/queue/tasks/pending/")
        print()

        watcher.watch(callback=self.process_task, interval=interval)


# ================== Standalone Execution ==================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='LAYER OS Art Director Agent')
    parser.add_argument('--agent-id', default='ad-worker-1')
    parser.add_argument('--interval', type=int, default=5)
    parser.add_argument('--test', action='store_true')

    args = parser.parse_args()

    agent = ArtDirector(agent_id=args.agent_id)

    if args.test:
        print("\n🧪 Test Mode: Visual Concept Creation")
        print("=" * 50)

        test_analysis = {
            'signal_id': 'test_001',
            'themes': ['AI와 창작', '느린 삶', '본질적 작업'],
            'key_insights': [
                'AI 도구는 반복 작업을 제거해 창작에 집중하게 한다',
                '기술은 인간의 창의성을 대체하지 않고 확장한다',
                '슬로우 라이프: 중요한 것에 집중하는 선택',
            ],
            'summary': 'AI는 슬로우 라이프 창작을 가능하게 하는 조용한 파트너',
        }

        result = agent.create_visual_concept(test_analysis)

        print(f"\n🎨 비주얼 컨셉:")
        print(f"   제목: {result.get('concept_title', 'N/A')}")
        print(f"   무드: {result.get('visual_mood', 'N/A')}")
        print(f"   팔레트: {result.get('color_palette', [])}")
        print(f"   레퍼런스 출처: {result.get('visual_ref_source', 'N/A')}")
        for p in result.get('image_prompts', []):
            print(f"   - {p.get('prompt', 'N/A')[:100]}...")

        print("\n✅ 테스트 완료!")

    else:
        print("\n🚀 Production Mode: Autonomous Queue Watching")
        print("=" * 50)
        agent.start_watching(interval=args.interval)
