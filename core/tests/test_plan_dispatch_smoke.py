#!/usr/bin/env python3
"""
plan_dispatch --smoke 통합 테스트
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLAN_DISPATCH = PROJECT_ROOT / "core" / "scripts" / "plan_dispatch.sh"


def _run_plan_dispatch(task: str, mode: str = "auto", extra_env: dict | None = None) -> dict:
    assert mode in {"auto", "manual"}
    cmd = ["bash", str(PLAN_DISPATCH), task, f"--{mode}", "--smoke"]
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    payload = json.loads(proc.stdout)
    assert isinstance(payload, dict)
    return payload


def test_auto_simple_task_skips_dispatcher_execution():
    payload = _run_plan_dispatch("ok", mode="auto")
    dispatcher = payload["dispatcher"]
    assert dispatcher["executed"] is False
    assert dispatcher["reason"] == "simple_task"
    assert dispatcher["complexity"] == "simple"


def test_auto_nontrivial_task_executes_dispatcher():
    payload = _run_plan_dispatch(
        "스킬 및 기본 툴 체계를 분석하고 업그레이드 항목을 구현한다",
        mode="auto",
    )
    dispatcher = payload["dispatcher"]
    assert dispatcher["executed"] is True
    assert dispatcher["complexity"] in {"medium", "high"}
    consensus = payload["consensus"]
    assert consensus["status"] in {"smoke", "ready", "degraded"}


def test_manual_mode_executes_even_with_short_task():
    payload = _run_plan_dispatch("ok", mode="manual")
    dispatcher = payload["dispatcher"]
    assert dispatcher["executed"] is True
    assert dispatcher["reason"] == "smoke_mode"


def test_auto_fallback_when_classifier_output_is_invalid_json(tmp_path):
    bad_classifier = tmp_path / "bad_classifier.py"
    bad_classifier.write_text("print('not-json')\n", encoding="utf-8")

    payload = _run_plan_dispatch(
        "스킬 및 기본 툴 체계를 분석하고 업그레이드 항목을 구현한다",
        mode="auto",
        extra_env={"PLAN_DISPATCH_CLASSIFIER_SCRIPT": str(bad_classifier)},
    )
    dispatcher = payload["dispatcher"]
    assert dispatcher["executed"] is False
    assert dispatcher["reason"] == "simple_task"
    assert dispatcher["complexity"] == "simple"


def test_manual_lite_fallback_marks_metrics_and_pending(tmp_path):
    fake_council = tmp_path / "fake_council.py"
    fake_council.write_text(
        "\n".join(
            [
                "import json",
                "payload = {",
                "  'timestamp': '2026-03-04T00:00:00+00:00',",
                "  'consensus': {",
                "    'status': 'degraded',",
                "    'models_used': [],",
                "    'runtime': {'gate_recommendation': 'hard_stop'}",
                "  }",
                "}",
                "print(json.dumps(payload, ensure_ascii=False))",
                "raise SystemExit(1)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    fake_lite = tmp_path / "fake_lite.py"
    fake_lite.write_text(
        "\n".join(
            [
                "import json",
                "payload = {",
                "  'timestamp': '2026-03-04T00:00:00+00:00',",
                "  'mode': 'preflight-lite',",
                "  'task': 'fallback-task',",
                "  'consensus': {",
                "    'status': 'degraded-lite',",
                "    'models_used': [],",
                "    'planner_primary': 'offline',",
                "    'verifier_secondary': 'offline',",
                "    'intent': 'fallback-task',",
                "    'approach': 'offline fallback',",
                "    'steps': [],",
                "    'risks': [],",
                "    'checks': [],",
                "    'decision': 'go'",
                "  }",
                "}",
                "print(json.dumps(payload, ensure_ascii=False))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    metrics_log = tmp_path / "metrics.jsonl"
    pending_log = tmp_path / "pending.jsonl"
    task = "플랜 카운슬 실패 경로 fallback 검증을 위한 비자명 태스크"
    env = os.environ.copy()
    env.update(
        {
            "PLAN_DISPATCH_COUNCIL_SCRIPT": str(fake_council),
            "PLAN_DISPATCH_COUNCIL_LITE_SCRIPT": str(fake_lite),
            "PLAN_DISPATCH_AUTO_LITE_FALLBACK": "1",
            "PLAN_DISPATCH_COUNCIL_RETRIES": "1",
            "PLAN_DISPATCH_METRICS_LOG": str(metrics_log),
            "PLAN_DISPATCH_PENDING_LOG": str(pending_log),
            "PLAN_DISPATCH_LOG_PENDING": "1",
            "PLAN_DISPATCH_LOG_METRICS": "1",
        }
    )

    proc = subprocess.run(
        ["bash", str(PLAN_DISPATCH), task, "--manual"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 3, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    payload = json.loads(proc.stdout)
    assert payload["dispatcher"]["reason"] == "hard_stop_fallback_lite"

    metric_rows = [
        json.loads(line)
        for line in metrics_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert metric_rows
    last_metric = metric_rows[-1]
    assert last_metric["reason"] == "hard_stop_fallback_lite"
    assert last_metric["fallback"] is True

    pending_rows = [
        json.loads(line)
        for line in pending_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert pending_rows
    assert pending_rows[-1]["reason"] == "hard_stop_fallback_lite"
