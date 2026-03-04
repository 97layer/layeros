#!/usr/bin/env python3
"""
harness_doctor council-worker guard checks
"""

from __future__ import annotations

from pathlib import Path

from core.scripts import harness_doctor as hd


def test_council_worker_check_fails_when_required_and_inactive(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(hd, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("COUNCIL_WORKER_REQUIRED", "1")
    monkeypatch.setattr(hd.shutil, "which", lambda _: None)

    result = hd.check_council_worker()
    assert result.status == "fail"
    assert "inactive" in result.detail


def test_council_worker_check_passes_when_process_detected(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(hd, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("COUNCIL_WORKER_REQUIRED", "1")

    def _which(name: str) -> str | None:
        return "/usr/bin/pgrep" if name == "pgrep" else None

    def _run(cmd):
        if cmd and cmd[0] == "pgrep":
            return 0, "1234", ""
        return 1, "", ""

    monkeypatch.setattr(hd.shutil, "which", _which)
    monkeypatch.setattr(hd, "run_command", _run)

    result = hd.check_council_worker()
    assert result.status == "pass"
    assert "process:pgrep" in result.detail


def test_council_worker_check_warns_when_optional_and_inactive(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(hd, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("COUNCIL_WORKER_REQUIRED", "0")
    monkeypatch.setattr(hd.shutil, "which", lambda _: None)

    result = hd.check_council_worker()
    assert result.status == "warn"
    assert "inactive" in result.detail
