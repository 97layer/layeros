#!/usr/bin/env python3
"""
LAYER OS Intent Classifier
규칙 우선 분류 — 명확한 경우 API 호출 없음
"""

import json
import logging
import os
import re
from typing import Dict, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import google.genai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

logger = logging.getLogger(__name__)

# 명시적 저장 의도 패턴
_SIGNAL_PREFIXES = ('기록:', '저장:', '메모:', '인사이트:', '아이디어:', '노트:',
                    '기록해', '저장해', '메모해', '인사이트 -', '아이디어 -')
_URL_RE = re.compile(r'https?://')


class IntentClassifier:
    """
    분류 순서:
    1. 규칙 (즉시 — API 호출 없음): command, 명시적 signal, URL
    2. Gemini (모호한 경우만): 30~200자 메시지
    3. 기본값: conversation
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('GOOGLE_API_KEY')

        if GEMINI_AVAILABLE and self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            self._model_name = 'gemini-2.5-flash'
            self.use_ai = True
            logger.info("IntentClassifier ready (rule+AI)")
        else:
            self.client = None
            self.use_ai = False
            logger.warning("IntentClassifier: rule-only mode")

    def classify(self, text: str, user_context: Optional[Dict] = None) -> Dict:
        # 1. 명령어
        if text.startswith('/'):
            return _result('command', 1.0, 'slash command')

        # 2. URL → signal (링크 저장)
        if _URL_RE.search(text):
            return _result('insight', 0.95, 'contains URL')

        # 3. 명시적 저장 의도
        text_lower = text.lower().strip()
        if any(text_lower.startswith(p.lower()) for p in _SIGNAL_PREFIXES):
            return _result('insight', 0.95, 'explicit save prefix')

        # 4. 짧은 메시지 (<= 20자) → 항상 conversation
        if len(text) <= 20:
            return _result('conversation', 0.9, 'short message')

        # 5. 매우 긴 텍스트 (>500자) → 에세이/메모 → insight로 직처리
        if len(text) > 500:
            return _result('insight', 0.85, 'long text — essay/memo')

        # 6. 모호한 중간 길이 → Gemini 판단
        if self.use_ai and 30 <= len(text) <= 500:
            result = self._classify_with_ai(text)
            if result:
                return result

        # 7. 기본값: conversation
        return _result('conversation', 0.7, 'default')

    def _classify_with_ai(self, text: str) -> Optional[Dict]:
        try:
            prompt = f"""메시지를 분류하라.

메시지: "{text}"

분류:
- insight: 순호가 명확히 기록/저장하려는 아이디어, 생각, 관찰. 구체적 내용 있음.
- conversation: 질문, 반응, 대화, 명령, 피드백. 불확실하면 무조건 여기.

JSON만:
{{"intent": "insight 또는 conversation", "confidence": 0.0~1.0, "reasoning": "한 줄"}}"""

            resp = self.client.models.generate_content(model=self._model_name, contents=[prompt])
            m = re.search(r'\{.*\}', resp.text, re.DOTALL)
            if m:
                data = json.loads(m.group())
                intent = data.get('intent', 'conversation')
                if intent not in ('insight', 'conversation'):
                    intent = 'conversation'
                return _result(intent, float(data.get('confidence', 0.7)), data.get('reasoning', ''))
        except Exception as e:
            logger.warning("AI 분류 실패: %s", e)
        return None


def _result(intent: str, confidence: float, reasoning: str) -> Dict:
    return {'intent': intent, 'confidence': confidence, 'reasoning': reasoning}


# Singleton
_classifier: Optional[IntentClassifier] = None


def get_intent_classifier() -> IntentClassifier:
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier
