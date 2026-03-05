import argparse
import json

from core.system import session_state


def test_session_state_start_and_finish(tmp_path, monkeypatch):
    state_path = tmp_path / "system_state.json"
    monkeypatch.setattr(session_state, "SYSTEM_STATE_PATH", state_path)

    start_args = argparse.Namespace(
        event="start",
        agent_id="Codex",
        task_label="bootstrap-check",
        session_id="sess-1",
        summary="",
    )
    assert session_state.cmd_start(start_args) == 0

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["sessions"]["sess-1"]["status"] == "active"
    assert data["sessions"]["sess-1"]["task_label"] == "bootstrap-check"

    finish_args = argparse.Namespace(
        event="finish",
        agent_id="Codex",
        task_label="handoff-done",
        session_id="sess-1",
        summary="completed summary",
    )
    assert session_state.cmd_finish(finish_args) == 0

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["sessions"]["sess-1"]["status"] == "completed"
    assert data["sessions"]["sess-1"]["task_label"] == "handoff-done"
    assert data["sessions"]["sess-1"]["summary"] == "completed summary"
