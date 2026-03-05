#!/usr/bin/env python3
"""
Tests for council_issue_loop.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.scripts import council_issue_loop as loop


def _write_council_room(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_sync_creates_pending_for_unresolved_proposals(tmp_path: Path):
    room = tmp_path / "knowledge" / "agent_hub" / "council_room.md"
    _write_council_room(
        room,
        """
## [2026-03-05 00:00] 안건 — 첫 번째
**proposal_id**: `issue_alpha`
본문

## [2026-03-05 00:10] 안건 — 두 번째
**proposal_id**: `issue_beta`
본문
- [2026-03-05 00:15] ✅ 처리 완료 (proposal=issue_beta) by SA
""".strip()
        + "\n",
    )

    paths = loop.build_paths(tmp_path)
    result = loop.sync_from_council_room(paths)

    assert result["created"] == ["issue_alpha"]
    pending = loop.list_queue_items(paths.pending_dir)
    assert set(pending.keys()) == {"issue_alpha"}
    payload = pending["issue_alpha"][1]
    assert payload["title"] == "첫 번째"
    assert payload["status"] == "pending"


def test_claim_then_resolve_deletes_issue_and_logs(tmp_path: Path):
    room = tmp_path / "knowledge" / "agent_hub" / "council_room.md"
    _write_council_room(
        room,
        """
## [2026-03-05 01:00] 안건 — 순환 테스트
**proposal_id**: `issue_rotate`
본문
""".strip()
        + "\n",
    )
    paths = loop.build_paths(tmp_path)
    loop.sync_from_council_room(paths)

    claimed = loop.claim_issue(paths, "issue_rotate", "CODEX")
    assert claimed["state"] == "processing"
    assert claimed["claimed_by"] == "CODEX"

    resolved = loop.resolve_issue(paths, "issue_rotate", "CODEX", "done")
    assert resolved["deleted"] is True

    state = loop.queue_state(paths)
    assert "issue_rotate" not in state["pending"]
    assert "issue_rotate" not in state["processing"]
    assert "issue_rotate" not in state["completed"]

    room_text = paths.council_room.read_text(encoding="utf-8")
    assert "(proposal=issue_rotate)" in room_text
    assert "by CODEX" in room_text

    events = paths.event_log.read_text(encoding="utf-8").splitlines()
    assert any('"event": "claimed"' in line for line in events)
    assert any('"event": "resolved"' in line for line in events)


def test_resolve_requires_owner_unless_forced(tmp_path: Path):
    room = tmp_path / "knowledge" / "agent_hub" / "council_room.md"
    _write_council_room(
        room,
        """
## [2026-03-05 02:00] 안건 — 권한 테스트
**proposal_id**: `issue_owner`
본문
""".strip()
        + "\n",
    )
    paths = loop.build_paths(tmp_path)
    loop.sync_from_council_room(paths)
    loop.claim_issue(paths, "issue_owner", "SA")

    with pytest.raises(PermissionError):
        loop.resolve_issue(paths, "issue_owner", "CE", "done")

    forced = loop.resolve_issue(paths, "issue_owner", "CE", "done", force=True)
    assert forced["state"] == "completed"


def test_sync_prunes_resolved_by_decision_log(tmp_path: Path):
    room = tmp_path / "knowledge" / "agent_hub" / "council_room.md"
    _write_council_room(
        room,
        """
## [2026-03-05 03:00] 안건 — 로그 정리
**proposal_id**: `issue_prune`
본문
""".strip()
        + "\n",
    )
    paths = loop.build_paths(tmp_path)
    first = loop.sync_from_council_room(paths)
    assert "issue_prune" in first["created"]

    paths.decision_log.parent.mkdir(parents=True, exist_ok=True)
    paths.decision_log.write_text(
        json.dumps({"type": "council_reject", "id": "issue_prune"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    second = loop.sync_from_council_room(paths)
    assert any(item.endswith(":issue_prune") for item in second["pruned"])
    assert "issue_prune" not in loop.list_queue_items(paths.pending_dir)


def test_resolve_requires_claim_first(tmp_path: Path):
    room = tmp_path / "knowledge" / "agent_hub" / "council_room.md"
    _write_council_room(
        room,
        """
## [2026-03-05 04:00] 안건 — 선클레임 강제
**proposal_id**: `issue_need_claim`
본문
""".strip()
        + "\n",
    )
    paths = loop.build_paths(tmp_path)
    loop.sync_from_council_room(paths)

    with pytest.raises(PermissionError):
        loop.resolve_issue(paths, "issue_need_claim", "CODEX", "done")

    forced = loop.resolve_issue(paths, "issue_need_claim", "CODEX", "done", force=True)
    assert forced["state"] == "completed"


def test_claim_timeout_when_issue_lock_is_held(tmp_path: Path):
    room = tmp_path / "knowledge" / "agent_hub" / "council_room.md"
    _write_council_room(
        room,
        """
## [2026-03-05 05:00] 안건 — 락 경합
**proposal_id**: `issue_locked`
본문
""".strip()
        + "\n",
    )
    paths = loop.build_paths(tmp_path)
    loop.sync_from_council_room(paths)
    loop.ensure_dirs(paths)

    lock_file = paths.locks_dir / f"{loop.sanitize_issue_id('issue_locked')}.lock"
    lock_file.write_text("held\n", encoding="utf-8")

    with pytest.raises(TimeoutError):
        loop.claim_issue(paths, "issue_locked", "CODEX", lock_timeout=0.02)
