#!/usr/bin/env python3
"""
proactive_scan.py — 에이전트 능동 사고 레이어

실행 전 3단계 스캔:
  ① SIDE EFFECTS — 이 액션이 건드리는 파일/서비스/데이터
  ② BLIND SPOTS  — 에이전트가 모르는 것 (상태 미확인, FROZEN 경계)
  ③ SIMPLER PATH — 더 짧거나 더 좋은 경로

경고가 있으면 → 실행 전 로그
FROZEN 침범이면 → 즉시 중단

Usage:
    class MyAgent(ProactiveScan):
        def _side_effects(self, action, ctx): ...
        def _blind_spots(self, action, ctx): ...
        def _simpler_path(self, action, ctx): ...

        def do_work(self):
            warnings = self.scan("do_work", {"target_file": "..."})
            # proceed regardless (FROZEN만 RuntimeError)
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 권한 경계 (gardener.py FROZEN 상수와 동기화)
FROZEN_FILES = {"the_origin.md", "sage_architect.md"}
PROPOSE_FILES = {"practice.md"}

# Ralph Loop Loop3 금지 패턴 (sage_architect.md §6.5)
_CLICHE_A = re.compile(r"중요합니다|필요합니다|생각합니다|가능합니다|좋습니다")
_CLICHE_B = re.compile(r"여러분|함께|소통|공유|연결|관계|우리\s*모두")
_CLICHE_C = re.compile(r"정말|너무|매우|아주|진짜|엄청|굉장히")
_TEMPORAL  = re.compile(r"현재|요즘|최근|오늘날|이 시대|이 시기|트렌드|유행|밀레니얼|MZ세대")

logger = logging.getLogger(__name__)


class ProactiveScan:
    """
    능동 사고 믹스인. 서브클래스에서 3개 메서드 오버라이드.
    모든 에이전트의 주요 실행 전 scan() 호출.
    """

    # ── 공개 API ─────────────────────────────────────────────────────────

    def scan(self, action: str, ctx: dict[str, Any] | None = None) -> list[str]:
        """
        실행 전 스캔. 경고 목록 반환.
        비어있으면 즉시 실행. 있으면 로그 후 실행 (FROZEN 제외).
        """
        ctx = ctx or {}
        warnings: list[str] = []
        warnings += self._side_effects(action, ctx)
        warnings += self._blind_spots(action, ctx)
        warnings += self._simpler_path(action, ctx)

        agent_id = getattr(self, "agent_id", getattr(self, "agent_type", "?"))
        for msg in warnings:
            logger.warning("[%s] SCAN ▸ %s", agent_id, msg)

        # FROZEN 침범 = 즉시 중단
        fatal = [w for w in warnings if "FROZEN" in w]
        if fatal:
            raise RuntimeError(f"[ProactiveScan] 실행 중단: {fatal[0]}")

        return warnings

    # ── 서브클래스 오버라이드 지점 ────────────────────────────────────────

    def _side_effects(self, action: str, ctx: dict) -> list[str]:
        """이 액션이 건드리는 파일/서비스. 기본: FROZEN/PROPOSE 감지."""
        warnings = []
        target = ctx.get("target_file", "")
        if target:
            fname = Path(target).name
            if fname in FROZEN_FILES:
                warnings.append(f"SIDE EFFECT: FROZEN 파일 접근 시도 — {fname}")
            elif fname in PROPOSE_FILES:
                warnings.append(f"SIDE EFFECT: PROPOSE 파일 — {fname} (순호 승인 필요)")
        return warnings

    def _blind_spots(self, action: str, ctx: dict) -> list[str]:
        """에이전트가 모르는 것. 기본: work_lock 확인."""
        return _check_work_lock()

    def _simpler_path(self, action: str, ctx: dict) -> list[str]:
        """더 짧은 경로. 기본: 없음 (서브클래스에서 구현)."""
        return []

    # ── 공유 유틸리티 (에이전트에서 직접 호출 가능) ──────────────────────

    @staticmethod
    def check_ralph_loop(text: str) -> list[str]:
        """
        Ralph Loop 사전 스캔 (sage_architect.md §6.5).
        에세이 생성 전 클리셰/시대어 패턴 감지.
        Returns warning strings.
        """
        warnings = []
        if _TEMPORAL.search(text):
            found = _TEMPORAL.findall(text)
            warnings.append(f"Ralph Loop1 위험: 시대 한정 표현 {found}")
        if _CLICHE_A.search(text):
            found = _CLICHE_A.findall(text)
            warnings.append(f"Ralph Loop3 위험: 빈 공감 표현 {found}")
        if _CLICHE_C.search(text):
            found = _CLICHE_C.findall(text)
            warnings.append(f"Ralph Loop3 위험: 강조 부사 {found}")
        return warnings

    @staticmethod
    def check_brand_voice(text: str) -> list[str]:
        """
        브랜드 보이스 위반 사전 감지 (sage_architect.md §9).
        텔레그램 응답 / 에세이 전 호출.
        """
        FORBIDDEN = [
            "트렌드", "유행", "핫한", "최고", "최상", "베스트",
            "성공", "성취", "정복", "레벨업", "업그레이드",
            "효율", "생산성", "ROI", "꿀팁", "노하우", "공략",
            "힐링", "치유", "행복", "만족", "기쁨",
            "특별한", "특별함",
        ]
        found = [w for w in FORBIDDEN if w in text]
        if found:
            return [f"BRAND VOICE 위반: 금지어 감지 {found}"]
        return []


# ── 모듈 레벨 유틸 ────────────────────────────────────────────────────────

def _check_work_lock() -> list[str]:
    """work_lock.json 상태 확인. 잠김이면 경고 반환."""
    lock_path = PROJECT_ROOT / "knowledge" / "system" / "work_lock.json"
    if not lock_path.exists():
        return []
    try:
        with open(lock_path) as f:
            lock = json.load(f)
        if lock.get("locked"):
            reason = lock.get("reason", "사유 없음")
            return [f"BLIND SPOT: work_lock 잠김 — {reason}"]
    except Exception:
        pass
    return []
