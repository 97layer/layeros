#!/usr/bin/env python3
"""
MacBook Heartbeat Monitor — LAYER OS

역할:
  - MacBook 측에서 30초마다 knowledge/system/execution_context.json 갱신
  - GCP VM이 이 파일을 감시하여 Mac 오프라인 감지 → active_executor: cloud 전환
  - SHA256 변경 감지로 불필요한 쓰기 방지 (gcp_realtime_push.py 패턴 재활용)

실행 위치: MacBook (로컬) — 컨테이너 외부
실행 방법: python core/system/heartbeat.py [--once]
"""

import json
import time
import hashlib
import logging
import argparse
from pathlib import Path
from datetime import datetime

# 경로 설정
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONTEXT_FILE = PROJECT_ROOT / "knowledge" / "system" / "execution_context.json"
SYSTEM_STATE_FILE = PROJECT_ROOT / "knowledge" / "system" / "system_state.json"

# 설정
HEARTBEAT_INTERVAL = 30          # 초
FAILOVER_THRESHOLD = 120         # 이 시간(초) 이상 heartbeat 없으면 failover

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Heartbeat] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def _calc_hash(data: dict) -> str:
    """딕셔너리의 SHA256 해시 반환. 변경 감지에 사용."""
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


def read_context() -> dict:
    """execution_context.json 읽기. 없으면 기본값 반환."""
    if CONTEXT_FILE.exists():
        try:
            return json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    # 기본 구조
    return {
        "active_executor": "local",
        "last_heartbeat": None,
        "mac_status": "unknown",
        "gcp_status": "standby",
        "current_task": None,
        "failover_threshold_seconds": FAILOVER_THRESHOLD,
    }


def write_context(ctx: dict) -> None:
    """execution_context.json 원자적 쓰기."""
    CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONTEXT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(ctx, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CONTEXT_FILE)  # atomic rename


def _update_system_state(heartbeat_iso: str) -> None:
    """
    Keep system_state.json heartbeat metadata fresh alongside execution_context.
    Best-effort only; failures are logged and ignored.
    """
    if not SYSTEM_STATE_FILE.exists():
        return
    try:
        state = json.loads(SYSTEM_STATE_FILE.read_text(encoding="utf-8"))
        agents = state.setdefault("agents", {})

        td = agents.setdefault("Technical_Director", {})
        td["status"] = "ACTIVE"
        td["last_heartbeat"] = heartbeat_iso
        td.setdefault("location", "Local(Mac)")
        td.setdefault("current_task", "시스템 상태 점검 및 태스크 스캔")

        async_bot = agents.get("Async_Telegram_Bot")
        if isinstance(async_bot, dict):
            async_bot["last_heartbeat"] = heartbeat_iso

        state["last_update"] = heartbeat_iso.replace("T", " ")[:19]
        previous_note = str(state.get("status_note", "")).lower()
        if str(state.get("system_status", "")).upper() == "DEGRADED" and "heartbeat" in previous_note:
            state["system_status"] = "HEALTHY"
        state["status_note"] = f"Heartbeats refreshed at {state['last_update']}"

        tmp = SYSTEM_STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(SYSTEM_STATE_FILE)
    except Exception as exc:  # noqa: BLE001
        logger.warning("system_state heartbeat sync skipped: %s", exc)


def update_heartbeat() -> bool:
    """
    MacBook heartbeat 갱신.

    변경이 없으면 파일 쓰기를 건너뜀 (Drive sync 트리거 최소화).
    반환값: True=파일 업데이트 됨, False=변경 없음
    """
    ctx = read_context()
    prev_hash = _calc_hash(ctx)

    now = datetime.now().isoformat()
    ctx["last_heartbeat"] = now
    ctx["mac_status"] = "online"
    ctx["active_executor"] = "local"
    ctx["failover_threshold_seconds"] = FAILOVER_THRESHOLD

    if _calc_hash(ctx) == prev_hash:
        return False  # 변경 없음

    write_context(ctx)
    _update_system_state(now)
    return True


def check_failover_needed() -> bool:
    """
    GCP VM 측에서 호출: Mac heartbeat가 끊겼는지 판단.

    반환값: True=failover 필요 (Mac 오프라인), False=Mac 정상
    """
    ctx = read_context()
    last = ctx.get("last_heartbeat")
    if not last:
        return True  # heartbeat 기록 없음

    try:
        last_dt = datetime.fromisoformat(last)
        elapsed = (datetime.now() - last_dt).total_seconds()
        threshold = ctx.get("failover_threshold_seconds", FAILOVER_THRESHOLD)
        return elapsed > threshold
    except (ValueError, TypeError):
        return True


def set_executor(executor: str) -> None:
    """active_executor 수동 변경 (local | cloud)."""
    assert executor in ("local", "cloud"), f"Invalid executor: {executor}"
    ctx = read_context()
    ctx["active_executor"] = executor
    if executor == "cloud":
        ctx["mac_status"] = "offline"
    write_context(ctx)
    logger.info("active_executor → %s", executor)


def run_daemon() -> None:
    """
    MacBook 측 데몬 루프.
    30초마다 heartbeat 갱신. Ctrl+C로 종료.
    """
    logger.info(
        "Heartbeat daemon 시작 (interval=%ds, failover_threshold=%ds)",
        HEARTBEAT_INTERVAL,
        FAILOVER_THRESHOLD,
    )

    try:
        while True:
            updated = update_heartbeat()
            if updated:
                logger.info("Heartbeat 갱신: %s", datetime.now().strftime("%H:%M:%S"))
            time.sleep(HEARTBEAT_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Heartbeat daemon 종료.")
        # Mac 오프라인 상태로 마킹
        ctx = read_context()
        ctx["mac_status"] = "offline"
        write_context(ctx)


def run_once() -> None:
    """heartbeat 1회만 갱신하고 종료. 스크립트/테스트 용도."""
    updated = update_heartbeat()
    status = "갱신됨" if updated else "변경 없음"
    logger.info("Heartbeat 1회 실행: %s", status)


# ─── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LAYER OS Heartbeat Monitor")
    parser.add_argument(
        "--once",
        action="store_true",
        help="1회 heartbeat 갱신 후 종료 (데몬 없이 테스트)",
    )
    parser.add_argument(
        "--check-failover",
        action="store_true",
        help="Mac heartbeat 끊김 여부 확인 (GCP 측 체크)",
    )
    parser.add_argument(
        "--set-executor",
        choices=["local", "cloud"],
        help="active_executor 수동 변경",
    )
    args = parser.parse_args()

    if args.once:
        run_once()
    elif args.check_failover:
        needed = check_failover_needed()
        print("failover_needed:", needed)
    elif args.set_executor:
        set_executor(args.set_executor)
    else:
        run_daemon()
