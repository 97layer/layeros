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


def test_council_worker_pending_count_includes_council_room_queue(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(hd, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("COUNCIL_WORKER_REQUIRED", "1")
    monkeypatch.setattr(hd.shutil, "which", lambda _: None)

    pending = tmp_path / ".infra" / "queue" / "council_room" / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    (pending / "issue-1.json").write_text("{}", encoding="utf-8")

    result = hd.check_council_worker()
    assert result.status == "fail"
    assert "pending=1" in result.detail
    assert "council_room=1" in result.detail


def test_council_worker_check_passes_with_vm_status_active_timer(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(hd, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("COUNCIL_WORKER_REQUIRED", "1")

    def _which(name: str) -> str | None:
        # local macOS fallback path: no systemctl/pgrep probe, use deploy.sh --status output
        return None

    def _run(cmd):
        if cmd[:2] == ["bash", str(tmp_path / "core" / "scripts" / "deploy" / "deploy.sh")]:
            return 0, "council-worker            active(timer) (service=inactive timer=active)", ""
        return 1, "", ""

    deploy_sh = tmp_path / "core" / "scripts" / "deploy" / "deploy.sh"
    deploy_sh.parent.mkdir(parents=True, exist_ok=True)
    deploy_sh.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    monkeypatch.setattr(hd.shutil, "which", _which)
    monkeypatch.setattr(hd, "run_command", _run)

    result = hd.check_council_worker()
    assert result.status == "pass"
    assert "vm:deploy-status" in result.detail
