#!/usr/bin/env python3
"""
pipeline_resilience_smoke.py

SA → CE → CD를 fallback 모드로 연속 실행해
큐 정체 없이 completed까지 흐르는지 확인하는 스모크 검증.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from core.agents.ce_agent import ChiefEditor
from core.agents.cd_agent import CreativeDirector
from core.agents.sa_agent import StrategyAnalyst
from core.system.agent_watcher import AgentWatcher
from core.system.queue_manager import QueueManager


def queue_counts(queue_root: Path) -> Dict[str, int]:
    pending = len(list((queue_root / "tasks" / "pending").glob("*.json")))
    processing = len(list((queue_root / "tasks" / "processing").glob("*.json")))
    completed = len(list((queue_root / "tasks" / "completed").glob("*.json")))
    return {"pending": pending, "processing": processing, "completed": completed}


def load_completed(queue_root: Path, task_id: str) -> Dict[str, Any]:
    completed_file = queue_root / "tasks" / "completed" / f"{task_id}.json"
    if not completed_file.exists():
        raise FileNotFoundError(f"completed task not found: {completed_file}")
    return json.loads(completed_file.read_text(encoding="utf-8"))


def run_one(agent_type: str, agent_id: str, callback, interval: int) -> None:
    watcher = AgentWatcher(agent_type=agent_type, agent_id=agent_id)
    watcher.watch(callback=callback, interval=interval, max_iterations=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="SA/CE/CD resilience smoke")
    parser.add_argument("--interval", type=int, default=1, help="watch loop interval seconds")
    parser.add_argument("--allow-dirty-queue", action="store_true", help="pending/processing 존재 시에도 실행")
    parser.add_argument("--keep-signal", action="store_true", help="생성한 테스트 신호 파일 유지")
    args = parser.parse_args()

    os.environ.setdefault("SA_FORCE_FALLBACK", "1")
    os.environ.setdefault("CE_FORCE_FALLBACK", "1")
    os.environ.setdefault("CD_FORCE_FALLBACK", "1")

    qm = QueueManager()
    queue_root = qm.queue_root

    before = queue_counts(queue_root)
    if not args.allow_dirty_queue and (before["pending"] > 0 or before["processing"] > 0):
        raise RuntimeError(
            f"queue not clean before smoke: pending={before['pending']} processing={before['processing']}"
        )

    date_stamp = time.strftime("%Y%m%d")
    time_stamp = time.strftime("%H%M%S")
    signal_id = f"text_{date_stamp}_{time_stamp}"
    signal_path = PROJECT_ROOT / "knowledge" / "signals" / f"{signal_id}.json"
    signal_payload = {
        "signal_id": signal_id,
        "type": "text",
        "source": "smoke_test",
        "content": "fallback 경로에서도 파이프라인은 멈추지 않아야 한다.",
        "status": "raw",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "metadata": {"smoke": True},
    }
    signal_path.write_text(json.dumps(signal_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # 1) SA
    sa_task_id = qm.create_task(
        agent_type="SA",
        task_type="analyze_signal",
        payload={"signal_path": str(signal_path), "signal_id": signal_id},
    )
    sa = StrategyAnalyst(agent_id="sa-smoke")
    run_one("SA", "sa-smoke", sa.process_task, args.interval)
    sa_completed = load_completed(queue_root, sa_task_id)
    sa_result = sa_completed.get("result", {}).get("result", {})
    if sa_completed.get("status") != "completed":
        raise RuntimeError(f"SA task failed: {sa_task_id}")
    if sa_result.get("analysis_mode") != "fallback_local":
        raise RuntimeError(f"SA fallback not applied: {sa_result.get('analysis_mode')}")

    # 2) CE
    ce_task_id = qm.create_task(
        agent_type="CE",
        task_type="write_content",
        payload={
            "sa_result": sa_result,
            "visual_concept": {
                "concept_title": "Resilience Smoke",
                "visual_mood": "grounded",
                "brand_alignment": "fallback continuity",
            },
        },
    )
    ce = ChiefEditor(agent_id="ce-smoke")
    run_one("CE", "ce-smoke", ce.process_task, args.interval)
    ce_completed = load_completed(queue_root, ce_task_id)
    ce_result = ce_completed.get("result", {}).get("result", {})
    if ce_completed.get("status") != "completed":
        raise RuntimeError(f"CE task failed: {ce_task_id}")
    if ce_result.get("status") != "draft_for_cd":
        raise RuntimeError(f"CE draft status invalid: {ce_result.get('status')}")
    if ce_result.get("analysis_mode") != "fallback_local":
        raise RuntimeError(f"CE fallback not applied: {ce_result.get('analysis_mode')}")

    # 3) CD
    cd_task_id = qm.create_task(
        agent_type="CD",
        task_type="review_content",
        payload={
            "signal_id": signal_id,
            "sa_result": sa_result,
            "ad_result": {"concept_title": "Resilience Smoke"},
            "ce_result": ce_result,
            "ralph_score": 85,
        },
    )
    cd = CreativeDirector(agent_id="cd-smoke")
    run_one("CD", "cd-smoke", cd.process_task, args.interval)
    cd_completed = load_completed(queue_root, cd_task_id)
    cd_result = cd_completed.get("result", {}).get("result", {})
    if cd_completed.get("status") != "completed":
        raise RuntimeError(f"CD task failed: {cd_task_id}")
    if cd_result.get("review_mode") != "fallback_local":
        raise RuntimeError(f"CD fallback not applied: {cd_result.get('review_mode')}")
    if cd_result.get("decision") not in ("approve", "revise", "reject"):
        raise RuntimeError(f"CD decision invalid: {cd_result.get('decision')}")

    after = queue_counts(queue_root)
    if args.allow_dirty_queue:
        if after["pending"] > before["pending"] or after["processing"] > before["processing"]:
            raise RuntimeError(
                "queue regressed after smoke: "
                f"before(pending={before['pending']},processing={before['processing']}) "
                f"after(pending={after['pending']},processing={after['processing']})"
            )
    else:
        if after["pending"] > 0 or after["processing"] > 0:
            raise RuntimeError(
                f"queue not clean after smoke: pending={after['pending']} processing={after['processing']}"
            )

    if not args.keep_signal and signal_path.exists():
        signal_path.unlink()

    report = {
        "signal_id": signal_id,
        "tasks": {
            "sa": {"task_id": sa_task_id, "analysis_mode": sa_result.get("analysis_mode")},
            "ce": {
                "task_id": ce_task_id,
                "analysis_mode": ce_result.get("analysis_mode"),
                "status": ce_result.get("status"),
            },
            "cd": {
                "task_id": cd_task_id,
                "review_mode": cd_result.get("review_mode"),
                "decision": cd_result.get("decision"),
                "approved": cd_result.get("approved"),
            },
        },
        "queue_before": before,
        "queue_after": after,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
