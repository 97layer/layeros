from core.system.handoff import CURRENT_STATE_HEADER, replace_current_state_section


def test_replace_current_state_keeps_single_section():
    content = """# Header

Intro line.

## Other
Keep this section.

## 📍 현재 상태 (CURRENT STATE)

### [2026-03-01 10:00] Session Update - old-1

old one

## 📍 현재 상태 (CURRENT STATE)

### [2026-03-02 11:00] Session Update - old-2

old two

## Footer
tail
"""
    new_section = f"""{CURRENT_STATE_HEADER}

### [2026-03-05 10:00] Session Update - new

new state
"""
    updated = replace_current_state_section(content, new_section)
    assert updated.count(CURRENT_STATE_HEADER) == 1
    assert "old-1" not in updated
    assert "old-2" not in updated
    assert "## Other" in updated
    assert "## Footer" in updated
    assert "new state" in updated


def test_replace_current_state_appends_when_missing():
    content = """# Root

No current state yet.
"""
    new_section = f"""{CURRENT_STATE_HEADER}

### [2026-03-05 10:00] Session Update - new
"""
    updated = replace_current_state_section(content, new_section)
    assert updated.count(CURRENT_STATE_HEADER) == 1
    assert updated.startswith("# Root")
    assert updated.rstrip().endswith("Session Update - new")


def test_replace_current_state_for_empty_content():
    new_section = f"""{CURRENT_STATE_HEADER}

### [2026-03-05 10:00] Session Update - new
"""
    updated = replace_current_state_section("", new_section)
    assert updated.count(CURRENT_STATE_HEADER) == 1
    assert updated.strip().startswith(CURRENT_STATE_HEADER)
