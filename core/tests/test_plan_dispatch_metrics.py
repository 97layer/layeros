#!/usr/bin/env python3
"""
plan_dispatch_metrics 단위 테스트
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from core.system.plan_dispatch_metrics import append_metric, summarize_metrics


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLAN_METRICS_SCRIPT = PROJECT_ROOT / "core" / "system" / "plan_dispatch_metrics.py"


def test_append_and_summary_counts(tmp_path: Path):
    log_path = tmp_path / "plan_dispatch_metrics.jsonl"

    append_metric(
        log_path=log_path,
        task="스킬 및 기본 툴 체계를 분석하고 업그레이드 항목을 구현한다",
        mode="auto",
        phase="smoke",
        reason="smoke_mode",
        executed=True,
        complexity="medium",
        score=3,
        fallback=False,
    )
    append_metric(
        log_path=log_path,
        task="ok",
        mode="auto",
        phase="skip",
        reason="simple_task",
        executed=False,
        complexity="simple",
        score=0,
        fallback=True,
    )

    summary = summarize_metrics(log_path=log_path, window=100)
    assert summary["total"] == 2
    assert summary["executed_count"] == 1
    assert summary["fallback_count"] == 1
    assert summary["phase_counts"]["smoke"] == 1
    assert summary["phase_counts"]["skip"] == 1
    assert summary["reason_counts"]["simple_task"] == 1
    assert summary["complexity_counts"]["medium"] == 1
    assert summary["complexity_counts"]["simple"] == 1


def test_cli_respects_env_default_metrics_log(tmp_path: Path):
    env_log = tmp_path / "env_metrics.jsonl"
    env = os.environ.copy()
    env["PLAN_DISPATCH_METRICS_LOG"] = str(env_log)

    proc = subprocess.run(
        [
            "python3",
            str(PLAN_METRICS_SCRIPT),
            "--append",
            "--task",
            "env-default-log-check",
            "--mode",
            "manual",
            "--phase",
            "blocked",
            "--reason",
            "hard_stop_model_unavailable",
            "--executed",
            "false",
            "--complexity",
            "high",
            "--score",
            "4",
            "--fallback",
            "true",
            "--json",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert env_log.exists()
    rows = [line for line in env_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
