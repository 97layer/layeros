#!/usr/bin/env python3
"""
Council pending cleanup 검증

목표:
- 처리 완료된 proposal만 삭제
- 미처리 proposal은 유지
- dry-run에서는 실제 삭제하지 않음
"""

import json
from pathlib import Path

from core.system import council_manager as cm


def _write_pending(base: Path, proposal_id: str):
    (base / f"{proposal_id}.json").write_text(
        json.dumps({"proposal_id": proposal_id}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_reconcile_deletes_only_processed(monkeypatch, tmp_path):
    pending_dir = tmp_path / "council"
    room = tmp_path / "council_room.md"
    decision_log = tmp_path / "decision_log.jsonl"
    pending_dir.mkdir(parents=True, exist_ok=True)

    processed_by_log = "processed_log_1"
    processed_by_room = "processed_room_1"
    untouched = "pending_1"

    _write_pending(pending_dir, processed_by_log)
    _write_pending(pending_dir, processed_by_room)
    _write_pending(pending_dir, untouched)

    decision_log.write_text(
        "\n".join(
            [
                json.dumps(
                    {"type": "council_approve", "id": processed_by_log},
                    ensure_ascii=False,
                ),
                "not-a-json-line",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    room.write_text(
        f"- [2026-03-04 12:00] ✅ 승인 → CE task `x` (proposal={processed_by_room})\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(cm, "COUNCIL_PENDING_DIR", pending_dir)
    monkeypatch.setattr(cm, "COUNCIL_ROOM", room)
    monkeypatch.setattr(cm, "DECISION_LOG", decision_log)

    result = cm.CouncilManager().reconcile_pending_proposals(dry_run=False)

    assert set(result["deleted"]) == {processed_by_log, processed_by_room}
    assert result["skipped"] == [untouched]
    assert not (pending_dir / f"{processed_by_log}.json").exists()
    assert not (pending_dir / f"{processed_by_room}.json").exists()
    assert (pending_dir / f"{untouched}.json").exists()


def test_reconcile_dry_run_keeps_files(monkeypatch, tmp_path):
    pending_dir = tmp_path / "council"
    room = tmp_path / "council_room.md"
    decision_log = tmp_path / "decision_log.jsonl"
    pending_dir.mkdir(parents=True, exist_ok=True)

    proposal_id = "processed_dryrun_1"
    _write_pending(pending_dir, proposal_id)
    decision_log.write_text(
        json.dumps({"type": "council_reject", "id": proposal_id}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    room.write_text("", encoding="utf-8")

    monkeypatch.setattr(cm, "COUNCIL_PENDING_DIR", pending_dir)
    monkeypatch.setattr(cm, "COUNCIL_ROOM", room)
    monkeypatch.setattr(cm, "DECISION_LOG", decision_log)

    result = cm.CouncilManager().reconcile_pending_proposals(dry_run=True)

    assert result["deleted"] == [proposal_id]
    assert result["skipped"] == []
    assert (pending_dir / f"{proposal_id}.json").exists()
