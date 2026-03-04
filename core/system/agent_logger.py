#!/usr/bin/env python3
"""
LAYER OS Agent Event Logger
에이전트 활동을 JSONL 형식으로 실시간 기록 → Pixel Dashboard로 스트리밍

Author: LAYER OS + Claude Code
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


class AgentLogger:
    """
    에이전트 이벤트 로거

    Features:
    - JSONL 형식 로그 (timestamp, agent, action, target)
    - 파일별 분리 (.infra/logs/{agent_id}_events.jsonl)
    - 스레드 세이프 (flush=True)
    - 자동 디렉토리 생성

    Actions:
    - idle: 대기 중
    - read: 파일 읽기
    - write: 파일 쓰기
    - search: 검색/분석
    - think: 복잡한 처리
    - done: 작업 완료
    - error: 오류 발생
    """

    def __init__(
        self,
        agent_id: str,
        project_root: Optional[Path] = None,
        name: Optional[str] = None,
        log_dir: Optional[Path] = None,
        filename: Optional[str] = None,
    ):
        """
        Args:
            agent_id: 에이전트 식별자 (예: "ce", "sa", "gardener")
            project_root: 프로젝트 루트 경로 (None이면 자동 탐지)
            name: 로그에 사용할 별도 이름 (기본: agent_id)
            log_dir: 로그 디렉터리 강제 지정 (기본: .infra/logs)
            filename: 이벤트 로그 파일명 강제 지정
        """
        # 파일명/식별자
        self.agent_id = name or agent_id

        # 프로젝트 루트 탐지
        if project_root is None:
            project_root = Path(__file__).parent.parent.parent
        self.project_root = Path(project_root)

        # 로그 디렉토리
        self.log_dir = Path(log_dir) if log_dir else self.project_root / ".infra" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 이벤트 로그 파일
        self.event_log_path = (
            self.log_dir / filename if filename else self.log_dir / f"{agent_id}_events.jsonl"
        )

    def log_event(
        self,
        action: str,
        target: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        이벤트 기록

        Args:
            action: 액션 타입 (idle, read, write, search, think, done, error)
            target: 대상 (파일명, 쿼리, 에러 메시지 등)
            metadata: 추가 정보 (선택)
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.agent_id,
            "action": action,
        }

        if target:
            event["target"] = target

        if metadata:
            event["metadata"] = metadata

        # JSONL 추가 쓰기 (atomic)
        with open(self.event_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()  # 즉시 디스크 기록

    def idle(self, reason: Optional[str] = None):
        """대기 상태"""
        self.log_event("idle", target=reason)

    def read(self, file_path: str):
        """파일 읽기"""
        self.log_event("read", target=file_path)

    def write(self, file_path: str):
        """파일 쓰기"""
        self.log_event("write", target=file_path)

    def search(self, query: str):
        """검색/분석"""
        self.log_event("search", target=query)

    def think(self, task: str):
        """복잡한 처리"""
        self.log_event("think", target=task)

    def done(self, result: str):
        """작업 완료"""
        self.log_event("done", target=result)

    def error(self, error_msg: str):
        """오류 발생"""
        self.log_event("error", target=error_msg)

    def clear_log(self):
        """이벤트 로그 초기화 (디버깅용)"""
        if self.event_log_path.exists():
            self.event_log_path.unlink()

    # 레거시 호환: .log(...) → .log_event(...)
    def log(
        self,
        action: str,
        target: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """호환용 래퍼"""
        self.log_event(action, target=target, metadata=metadata)

    def get_recent_events(self, n: int = 10) -> list:
        """
        최근 N개 이벤트 조회

        Args:
            n: 조회할 이벤트 수

        Returns:
            최근 이벤트 리스트 (오래된 것부터)
        """
        if not self.event_log_path.exists():
            return []

        with open(self.event_log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 최근 N개 추출
        recent_lines = lines[-n:] if len(lines) >= n else lines

        events = []
        for line in recent_lines:
            try:
                events.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue

        return events


# ─── 전역 로거 인스턴스 (싱글톤 패턴) ───
_loggers = {}

def get_logger(agent_id: str, project_root: Optional[Path] = None) -> AgentLogger:
    """
    AgentLogger 싱글톤 getter

    Args:
        agent_id: 에이전트 ID
        project_root: 프로젝트 루트 (선택)

    Returns:
        AgentLogger 인스턴스
    """
    if agent_id not in _loggers:
        _loggers[agent_id] = AgentLogger(agent_id, project_root)
    return _loggers[agent_id]


# ─── 사용 예시 ───
if __name__ == "__main__":
    # 테스트
    logger = AgentLogger("test")

    logger.idle("대기 중")
    logger.think("에세이 주제 선정")
    logger.search("슬로우 라이프")
    logger.write("essay-011-freedom.html")
    logger.done("에세이 발행 완료")

    # 최근 이벤트 조회
    recent = logger.get_recent_events(5)
    print("\n최근 이벤트:")
    for event in recent:
        print(f"  [{event['timestamp']}] {event['agent']}: {event['action']} → {event.get('target', '-')}")
