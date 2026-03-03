#!/usr/bin/env python3
"""
LAYER OS Strategy Analyst (SA) Agent
Phase 6.2: Independent agent with Gemini Flash API

Role:
- Signal analysis and strategic insight extraction
- First responder to incoming signals
- Pattern recognition across signals
- Strategic recommendations

LLM: Gemini 2.5 Flash (Free tier, fast)
Queue: Autonomous task claiming via AgentWatcher
Output: Structured analysis → passed to AD/CE

Author: LAYER OS Technical Director
Updated: 2026-02-16 (google.genai SDK 마이그레이션)
"""

import logging
import os
import sys
import json
import time
import re
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Project setup
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.system.agent_watcher import AgentWatcher
from core.system.queue_manager import Task
from core.system.proactive_scan import ProactiveScan

# Using REST API directly - no SDK needed


class StrategyAnalyst(ProactiveScan):
    """
    Strategy Analyst Agent - Signal Analysis & Strategic Insights

    Capabilities:
    - Analyze incoming signals (text, links, images)
    - Extract strategic themes and patterns
    - Identify action items and opportunities
    - Generate initial insights for other agents
    """

    def __init__(self, agent_id: str = "sa-worker-1", api_key: Optional[str] = None):
        """
        Initialize Strategy Analyst

        Args:
            agent_id: Unique agent instance ID
            api_key: Google API key (or from env GOOGLE_API_KEY)
        """
        self.agent_id = agent_id
        self.agent_type = "SA"

        # Initialize Gemini API (REST API 직접 호출)
        self.api_key = api_key or os.getenv('GOOGLE_API_KEY')
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")

        self._model_name = 'gemini-2.5-flash'
        self._api_url = 'https://generativelanguage.googleapis.com/v1beta/models'

        # SA 에이전트 지침 로드
        self._persona = self._load_directive()

        logger.info("SA: 준비됨. (Key: ...%s)", self.api_key[-4:])

    def analyze_signal(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze incoming signal and extract strategic insights

        Args:
            signal_data: Signal content and metadata
                {
                    'signal_id': str,
                    'content': str,
                    'source': str (telegram, slack, etc.),
                    'timestamp': str,
                    'attachments': list (optional)
                }

        Returns:
            Analysis result with strategic insights
        """
        signal_id = signal_data.get('signal_id', 'unknown')
        content = signal_data.get('content', '')
        source = signal_data.get('source', 'unknown')

        logger.info("SA: 신호 %s 분석 시작. [API: %s]", signal_id, self._api_url)

        # ── 능동 사고 스캔 ──────────────────────────────────────
        self.scan("analyze_signal", {
            "signal_id": signal_id,
            "content": content,
            "source": source,
        })
        # ────────────────────────────────────────────────────────

        # Construct prompt for strategic analysis
        prompt = self._build_analysis_prompt(content, source)

        try:
            # Call Gemini API (REST API 직접 호출)
            import requests
            api_url = f"{self._api_url}/{self._model_name}:generateContent"
            headers = {"Content-Type": "application/json"}
            payload = {"contents": [{"parts": [{"text": prompt}]}]}

            response = requests.post(f"{api_url}?key={self.api_key}",
                                    headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            analysis_text = response.json()['candidates'][0]['content']['parts'][0]['text']

            # Parse structured response
            analysis = self._parse_analysis(analysis_text)

            # Add metadata
            analysis.update({
                'signal_id': signal_id,
                'analyzed_by': self.agent_id,
                'analyzed_at': datetime.now().isoformat(),
                'model': self._model_name,
                'source': source
            })

            score = analysis.get('strategic_score', 0)
            category = analysis.get('category', '')
            themes = ', '.join(analysis.get('themes', [])[:3])
            logger.info("SA: 완료. 점수 %s. 카테고리: %s. 테마: %s.", score, category, themes)

            # 자가발전: SA 분석 완료 → long_term_memory 피드백
            try:
                self._feedback_to_memory(analysis, content)
            except Exception as mem_e:
                logger.warning("Memory feedback skipped: %s", mem_e)

            # 자가발전: SA 분석 완료 → NotebookLM Signal Archive 저장
            try:
                self._save_to_notebooklm(analysis, content, source)
            except Exception as nlm_e:
                logger.warning("NotebookLM skipped: %s", nlm_e)

            # Corpus 누적: 신호 → 지식 풀 (군집 기반 발행을 위한 축적)
            try:
                from core.system.corpus_manager import CorpusManager
                corpus = CorpusManager()
                corpus.add_entry(signal_id, analysis, signal_data)
                logger.info("SA: Corpus 누적 완료 → %s", signal_id)
            except Exception as corpus_e:
                logger.warning("Corpus skipped: %s", corpus_e)

            # 신호 파일 status → analyzed (Orchestrator 중복 투입 방지)
            try:
                import pathlib
                signal_path = signal_data.get('signal_path') or str(
                    PROJECT_ROOT / 'knowledge' / 'signals' / f"{signal_id}.json"
                )
                sp = pathlib.Path(str(signal_path))
                if sp.exists():
                    sig_json = json.loads(sp.read_text())
                    sig_json['status'] = 'analyzed'
                    sig_json['analyzed_at'] = datetime.now().isoformat()
                    sp.write_text(json.dumps(sig_json, indent=2, ensure_ascii=False))
                    logger.info("SA: 신호 status -> analyzed: %s", signal_id)
            except Exception as upd_e:
                logger.warning("Signal status update skipped: %s", upd_e)

            return analysis

        except Exception as e:
            logger.error("SA: 분석 실패. %s", e)
            return {
                'signal_id': signal_id,
                'error': str(e),
                'status': 'failed'
            }

    # ── ProactiveScan 오버라이드 ──────────────────────────────────

    def _simpler_path(self, action: str, ctx: dict) -> list[str]:
        """SA: 빈 신호 또는 너무 짧은 신호 감지."""
        warnings = []
        content = ctx.get("content", "")
        if len(content.strip()) < 10:
            warnings.append("SIMPLER PATH: 신호 내용이 너무 짧음 — 분석 생략 고려")
        return warnings

    # ─────────────────────────────────────────────────────────────

    def _load_directive(self) -> str:
        """SA 에이전트 컨텍스트 로드 — directive_loader 기반 섹션 단위 추출"""
        try:
            from core.system.directive_loader import load_for_agent
            return load_for_agent("SA", max_total=4000)
        except ImportError:
            pass
        return "냉정하게 분석하라. 필요한 것만 말해라."

    def _feedback_to_memory(self, analysis: Dict[str, Any], original_content: str):
        """
        SA 분석 완료 후 long_term_memory.json에 인사이트 누적 — 자가발전 고리

        themes → concepts 카운트 누적
        key_insights + summary → experiences 추가
        strategic_score 80+ 만 저장 (노이즈 필터)
        """
        score = analysis.get('strategic_score', 0)
        if score < 50:
            return  # 노이즈는 기록 안 함

        lm_path = PROJECT_ROOT / 'knowledge' / 'long_term_memory.json'

        try:
            if lm_path.exists():
                data = json.loads(lm_path.read_text(encoding='utf-8'))
            else:
                data = {
                    'metadata': {'created_at': datetime.now().isoformat(), 'total_entries': 0},
                    'experiences': [],
                    'concepts': {},
                    'error_patterns': []
                }
        except Exception:
            return

        # themes → concepts 카운트 (빈도 = 중요도)
        for theme in analysis.get('themes', []):
            theme = theme.strip()
            if theme:
                data['concepts'][theme] = data['concepts'].get(theme, 0) + 1

        # category 도 concepts에 반영
        category = analysis.get('category', '')
        if category and category not in ('noise', 'unknown'):
            data['concepts'][f'SA:{category}'] = data['concepts'].get(f'SA:{category}', 0) + 1

        # experiences: summary + top insight 기록
        insights = analysis.get('key_insights', [])
        insight_preview = insights[0][:80] if insights else ''
        summary = analysis.get('summary', '')[:100]
        combined = f"[SA score:{score}] {summary}" + (f" | {insight_preview}" if insight_preview else '')

        data['experiences'].append({
            'summary': combined[:150],
            'category': 'SA분석',
            'timestamp': datetime.now().isoformat()[:16],
            'source': 'sa_agent',
            'score': score
        })

        # 최근 100개 유지
        if len(data['experiences']) > 100:
            data['experiences'] = data['experiences'][-100:]

        data['metadata']['total_entries'] = len(data['experiences'])
        data['metadata']['last_updated'] = datetime.now().isoformat()[:16]

        lm_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        logger.info("Memory updated: score=%s, themes=%s", score, analysis.get('themes', [])[:3])

    def _save_to_notebooklm(self, analysis: Dict[str, Any], content: str, source: str):
        """
        SA 분석 완료 후 NotebookLM Signal Archive에 저장.
        score 60+ 만 저장 (노이즈 제외).
        """
        score = analysis.get('strategic_score', 0)
        if score < 60:
            return

        try:
            from core.system.notebooklm_bridge import get_bridge, is_available
            if not is_available():
                return

            bridge = get_bridge()
            bridge.add_signal_to_archive({
                'signal_id': analysis.get('signal_id', ''),
                'content': content,
                'source': source,
                'analysis': analysis,
            })
            logger.info("NotebookLM 저장: score=%s", score)
        except ImportError:
            pass  # 브릿지 없으면 조용히 스킵

    def _build_analysis_prompt(self, content: str, source: str) -> str:
        """SA의 소거 렌즈로 신호 관찰 프롬프트 구성"""
        return f"""너는 SA이다. 97layer의 관찰자. 분석하지 않고 관찰한다.

{self._persona[:600]}

---

다음 신호를 소거 렌즈로 읽어라.
덜어낼 것을 찾는다. 사라지지 않고 남는 것을 찾는다.
설명하지 않는다. 보이는 것만 기록한다.

**신호 내용:**
{content}

**출처:** {source}

JSON 형식으로만 응답:
{{
  "strategic_score": <0-100, 97layer 본질과의 정렬도 — 느림·소거·공명 기준>,
  "category": "<trend|insight|opportunity|question|noise>",
  "content_category": "<Seeing|Living|Working|Making|Listening>",
  "themes": ["본질 키워드1", "본질 키워드2", "본질 키워드3"],
  "key_insights": [
    "관찰 1 — 신호에서 사라지지 않는 것 (한 문장)",
    "관찰 2 — 반복되는 패턴",
    "관찰 3 — 신호의 무게"
  ],
  "action_items": [
    "덜어낼 것 또는 주시할 것 1",
    "덜어낼 것 또는 주시할 것 2"
  ],
  "recommended_agents": ["AD", "CE", "CD"],
  "summary": "한 문장 — 신호의 본질만"
}}

**content_category 분류 기준:**
- Seeing: 철학, 관점, 감각적 관찰, 시선, 인식
- Living: 라이프스타일, 공간, 일상, 습관, 루틴
- Working: 직업, 미용, 아틀리에, 장인정신, 기술
- Making: 시스템, 브랜딩, 빌드, 프로세스, 코딩
- Listening: 관계, 공명, 대화, 타인, 연결

**관찰 기준 (소거 렌즈):**
- 80+: 신호가 느림·본질·여백·공명을 담고 있다. 더하지 않아도 무게가 있다.
- 50-79: 반복 빈도 주시. 공명 가능성 있음. 아직 판단 보류.
- 50 미만: 노이즈. 과잉 설명, 알고리즘 추종, 장식이 본질을 가린다.
- 신호에서 덜어낼수록 남는 것이 많을수록 높게 평가.
- 빠름·과장·설명 과잉·반복 자극 신호는 낮게 평가.

JSON만 출력. 설명 없이.
"""

    def _parse_analysis(self, analysis_text: str) -> Dict[str, Any]:
        """Parse Gemini response into structured data"""
        try:
            # Try to extract JSON from response
            # Sometimes Gemini wraps JSON in ```json ... ```
            if '```json' in analysis_text:
                json_start = analysis_text.find('```json') + 7
                json_end = analysis_text.find('```', json_start)
                json_text = analysis_text[json_start:json_end].strip()
            elif '```' in analysis_text:
                json_start = analysis_text.find('```') + 3
                json_end = analysis_text.find('```', json_start)
                json_text = analysis_text[json_start:json_end].strip()
            else:
                json_text = analysis_text.strip()

            analysis = json.loads(json_text)

            # Validate required fields
            required_fields = ['strategic_score', 'category', 'content_category', 'themes', 'key_insights', 'summary']
            for field in required_fields:
                if field not in analysis:
                    analysis[field] = None

            return analysis

        except json.JSONDecodeError as e:
            logger.warning("%s: Failed to parse JSON, using fallback", self.agent_id)
            return {
                'strategic_score': 50,
                'category': 'insight',
                'themes': ['unknown'],
                'key_insights': [analysis_text[:200]],
                'summary': analysis_text[:100],
                'raw_response': analysis_text,
                'parse_error': str(e)
            }

    def process_task(self, task: Task) -> Dict[str, Any]:
        """
        Process task from queue (callback for AgentWatcher)

        Args:
            task: Task from queue

        Returns:
            Task result
        """
        task_type = task.task_type
        payload = task.payload

        logger.info("%s: Processing task %s (%s)", self.agent_id, task.task_id, task_type)

        if task_type == 'analyze_signal':
            # signal_path가 있으면 파일 로드 (큐 payload엔 경로만 있음)
            signal_path = payload.get('signal_path')
            if signal_path:
                try:
                    from pathlib import Path as _Path
                    signal_data = json.loads(_Path(signal_path).read_text(encoding='utf-8'))
                except Exception as _e:
                    logger.warning("signal_path 로드 실패, payload 직접 사용: %s", _e)
                    signal_data = payload
            else:
                signal_data = payload

            # content 필드 정규화 (body/title 조합 fallback)
            if not signal_data.get('content'):
                title = signal_data.get('title', '')
                body = signal_data.get('body', '')
                signal_data['content'] = ("%s\n\n%s" % (title, body)).strip() if title else body

            # source 필드 정규화
            if not signal_data.get('source'):
                signal_data['source'] = signal_data.get('source_channel', 'unknown')

            result = self.analyze_signal(signal_data)
            return {
                'status': 'completed',
                'task_id': task.task_id,
                'result': result
            }

        elif task_type == 'batch_analyze':
            # Batch analysis (multiple signals)
            signals = payload.get('signals', [])
            results = []
            for signal in signals:
                analysis = self.analyze_signal(signal)
                results.append(analysis)

            return {
                'status': 'completed',
                'task_id': task.task_id,
                'results': results,
                'count': len(results)
            }

        else:
            return {
                'status': 'failed',
                'error': f"Unknown task type: {task_type}"
            }

    def start_watching(self, interval: int = 5):
        """
        Start autonomous queue watching

        Args:
            interval: Poll interval in seconds
        """
        watcher = AgentWatcher(
            agent_type=self.agent_type,
            agent_id=self.agent_id
        )

        logger.info("SA: 큐 감시 시작.")

        # Start watching (blocking)
        watcher.watch(
            callback=self.process_task,
            interval=interval
        )


# ================== Standalone Execution ==================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
    import argparse
    from core.system.env_validator import validate_env
    validate_env("sa_agent")

    parser = argparse.ArgumentParser(description='LAYER OS Strategy Analyst Agent')
    parser.add_argument('--agent-id', default='sa-worker-1', help='Agent instance ID')
    parser.add_argument('--interval', type=int, default=5, help='Queue poll interval (seconds)')
    parser.add_argument('--test', action='store_true', help='Run test mode (single analysis)')

    args = parser.parse_args()

    # Initialize agent
    try:
        agent = StrategyAnalyst(agent_id=args.agent_id)
    except ValueError as e:
        logger.error("Initialization failed: %s", e)
        logger.info("Set GOOGLE_API_KEY environment variable")
        sys.exit(1)

    if args.test:
        # Test mode: Single analysis
        logger.info("Test Mode: Single Signal Analysis")
        logger.info("=" * 50)

        test_signal = {
            'signal_id': 'test_001',
            'content': """
            I've been thinking about how AI tools are changing creative work.
            Instead of replacing creativity, they're removing the boring parts -
            research, formatting, repetitive tasks. This frees us to focus on
            what matters: ideas, connections, meaningful work. Maybe this aligns
            with slow living philosophy?
            """,
            'source': 'telegram',
            'timestamp': datetime.now().isoformat()
        }

        result = agent.analyze_signal(test_signal)

        logger.info("Analysis Result:")
        logger.info("   Strategic Score: %s", result.get('strategic_score', 'N/A'))
        logger.info("   Category: %s", result.get('category', 'N/A'))
        logger.info("   Themes: %s", ', '.join(result.get('themes', [])))
        logger.info("   Summary: %s", result.get('summary', 'N/A'))
        logger.info("   Key Insights:")
        for insight in result.get('key_insights', []):
            logger.info("   - %s", insight)

        logger.info("Test complete!")

    else:
        # Production mode: Autonomous queue watching
        logger.info("Production Mode: Autonomous Queue Watching")
        logger.info("=" * 50)
        agent.start_watching(interval=args.interval)
