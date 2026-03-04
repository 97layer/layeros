#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: agent_router.py
Author: 97LAYER Mercenary
Date: 2026-02-24
Description: 에이전트 디렉티브 로딩 및 메시지 기반 라우팅 (v2.0 — Brand OS 통합)
"""

import logging
import os
from typing import Optional, Dict

logger = logging.getLogger(__name__)

DIRECTIVES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "directives")
AGENT_REGISTRY: Dict[str, Dict[str, str]] = {
    # CD는 sage_architect.md §10에 흡수됨
    "AD": {"file": "practice.md", "section": "I-10", "name": "Art Director", "label": "AD"},
    "CE": {"file": "practice.md", "section": "II-11", "name": "Chief Editor", "label": "CE"},
    "SA": {"file": "practice.md", "section": "II-10", "name": "Strategy Analyst", "label": "SA"},
}

# 에이전트별 필독 문서 매핑 (practice.md 통합본)
AGENT_DIRECTIVES: Dict[str, list] = {
    "SA": [
        "practice.md",
    ],
    "CE": [
        "practice.md",
        "sage_architect.md",
    ],
    "AD": [
        "practice.md",
    ],
}

# 메시지 키워드 → 에이전트 매핑 (1차 필터)
KEYWORD_MAP: Dict[str, list] = {
    # CD 키워드는 CE로 흡수 (sage_architect.md 기반 판단)
    "AD": ["디자인", "UI", "로고", "시각", "레이아웃", "폰트", "색상", "이미지", "비주얼"],
    "CE": ["카피", "문구", "톤", "글", "콘텐츠", "에디토리얼", "매니페스토", "슬로건", "텍스트",
           "철학", "방향", "브랜드", "비전", "미션", "승인", "가치", "본질", "정체성"],
    "SA": ["트렌드", "분석", "데이터", "시장", "경쟁", "리서치", "인사이트", "통계", "조사"],
}


class AgentRouter:
    """에이전트 디렉티브 로딩 및 메시지 기반 라우팅"""

    def __init__(self, ai_engine=None):
        self.ai = ai_engine
        self.directives: Dict[str, str] = {}
        self.active_agent: Optional[str] = None
        self._load_all_directives()

        # Initialize SkillEngine for skill-based routing
        try:
            from libs.skill_engine import SkillEngine
            self.skill_engine = SkillEngine()
            logger.debug("SkillEngine initialized with %d skills", len(self.skill_engine.registry))
        except Exception as e:
            logger.warning("SkillEngine initialization failed: %s", e)
            self.skill_engine = None

    def _load_all_directives(self) -> None:
        """practice.md에서 에이전트 섹션 로드"""
        from core.system.directive_loader import load_section

        for key, info in AGENT_REGISTRY.items():
            section = info.get("section")
            content = load_section(info["file"], section, max_chars=3000)
            if content:
                self.directives[key] = content
                logger.debug("Loaded agent directive: %s (%s)", key, section)
            else:
                logger.error("Agent directive not found: %s %s", info["file"], section)

    def _load_brand_directives(self, agent_key: str) -> str:
        """에이전트별 Brand OS 문서 로드"""
        if agent_key not in AGENT_DIRECTIVES:
            return ""

        brand_docs = []
        for filename in AGENT_DIRECTIVES[agent_key]:
            filepath = os.path.join(DIRECTIVES_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    # 토큰 절약: 처음 1500자만
                    summary = content[:1500] + "..." if len(content) > 1500 else content
                    brand_docs.append("### %s\n%s\n" % (filename, summary))
            except FileNotFoundError:
                logger.warning("Brand directive not found: %s", filepath)

        return "\n".join(brand_docs) if brand_docs else ""

    def get_directive(self, agent_key: str) -> str:
        """특정 에이전트의 디렉티브 텍스트 반환"""
        return self.directives.get(agent_key, "")

    def set_agent(self, agent_key: str) -> bool:
        """수동 에이전트 전환"""
        agent_key = agent_key.upper()
        if agent_key in AGENT_REGISTRY:
            self.active_agent = agent_key
            logger.info("Agent switched to: %s", agent_key)
            return True
        return False

    def clear_agent(self) -> None:
        """에이전트 고정 해제 (자동 라우팅 모드)"""
        self.active_agent = None
        logger.info("Agent cleared. Auto-routing enabled.")

    def detect_skill(self, text: str) -> Optional[Dict]:
        """스킬 트리거 감지"""
        if not self.skill_engine:
            return None

        skill_id = self.skill_engine.detect_skill_from_input(text)
        if skill_id:
            skill = self.skill_engine.get_skill(skill_id)
            return {
                "skill_id": skill_id,
                "skill": skill,
                "engine": self.skill_engine
            }
        return None

    def route(self, text: str) -> str:
        """메시지를 분석하여 적절한 에이전트 키 반환"""
        # 0. 스킬 우선 라우팅
        skill_info = self.detect_skill(text)
        if skill_info:
            logger.info("Skill detected: %s", skill_info["skill_id"])
            return "SKILL:%s" % skill_info['skill_id']

        # 1. 수동 고정된 에이전트가 있으면 우선
        if self.active_agent:
            return self.active_agent

        # 2. 키워드 기반 1차 분류
        agent = self._keyword_match(text)
        if agent:
            return agent

        # 3. AI 기반 분류
        if self.ai and getattr(self.ai, 'api_key', None):
            agent = self._ai_classify(text)
            if agent:
                return agent

        # 4. 기본값: CE (편집장 — CD는 sage_architect.md에 흡수)
        return "CE"

    def _keyword_match(self, text: str) -> Optional[str]:
        """키워드 매칭으로 에이전트 분류"""
        scores: Dict[str, int] = {}
        for agent_key, keywords in KEYWORD_MAP.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[agent_key] = score

        if scores:
            return max(scores, key=scores.get)  # type: ignore
        return None

    def _ai_classify(self, text: str) -> Optional[str]:
        """AI를 사용하여 에이전트 분류"""
        prompt = (
            "다음 메시지를 처리할 LAYER OS 에이전트를 분류하시오.\n"
            "반드시 다음 중 하나만 출력하시오: CD, AD, CE, SA\n\n"
            "[에이전트 역할]\n"
            "- CD: 브랜드 철학, 전략 방향, 최종 승인\n"
            "- AD: 시각 디자인, UI/UX, 미학\n"
            "- CE: 카피라이팅, 톤앤매너, 에디토리얼\n"
            "- SA: 시장 분석, 트렌드, 데이터 리서치\n\n"
            '메시지: "%s"' % text
        )
        try:
            response = self.ai.generate_response(prompt).strip().upper()
            for key in AGENT_REGISTRY:
                if key in response:
                    return key
        except Exception as e:
            logger.error("Error in AI agent classification: %s", e)
        return None

    def build_system_prompt(self, agent_key: str) -> str:
        """에이전트 디렉티브 + Brand OS 문서를 포함한 system instruction 생성"""
        directive = self.get_directive(agent_key)
        agent_name = AGENT_REGISTRY.get(agent_key, {}).get("name", "Unknown")

        # Brand OS 문서 로드
        brand_directives = self._load_brand_directives(agent_key)

        return (
            "당신은 LAYER OS의 %s (%s)입니다.\n\n"
            "[Agent Directive]\n%s\n\n"
            "[Brand OS Directives]\n%s\n\n"
            "응답 원칙:\n"
            "1. Zero Noise: 이모지, 감탄사, 가식적인 사과를 금지. 즉시 본론.\n"
            "2. Anti-Hallucination: 실제 사실이 아닌 가상의 제약을 만들지 않는다.\n"
            "3. Cold Intelligence: 냉철한 분석과 실행 위주. 감정적 공감 연산 생략.\n"
            "4. Reality Grounding: 주어진 정보만 사실로 간주. 모르면 모른다고 한다.\n"
            "5. Brand OS Compliance: 모든 결정 전 Brand OS 문서 참조. 5 Pillars 기준."
        ) % (agent_name, agent_key, directive, brand_directives)

    def get_status(self) -> str:
        """현재 라우팅 상태 반환"""
        if self.active_agent:
            name = AGENT_REGISTRY[self.active_agent]["name"]
            return "고정 모드: %s (%s)" % (name, self.active_agent)
        return "자동 라우팅 모드 (메시지 기반 분류)"
