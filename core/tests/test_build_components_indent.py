#!/usr/bin/env python3
"""
build_components indentation regression tests.
"""

from pathlib import Path

from core.scripts import build_components as bc


def test_inject_components_preserves_marker_indent(monkeypatch, tmp_path: Path):
    website = tmp_path / "website"
    components = website / "_components"
    target = website / "about" / "index.html"
    components.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)

    (components / "nav.html").write_text(
        "<nav class=\"site-nav\">\n<ul><li>Archive</li></ul>\n</nav>\n",
        encoding="utf-8",
    )
    target.write_text(
        "\n".join(
            [
                "<html>",
                "<body>",
                "  <!-- COMPONENT:nav -->",
                "  <nav>legacy</nav>",
                "  <!-- /COMPONENT:nav -->",
                "</body>",
                "</html>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(bc, "WEBSITE_DIR", website)
    monkeypatch.setattr(bc, "COMPONENTS_DIR", components)
    monkeypatch.setattr(bc, "PROJECT_ROOT", tmp_path)

    changed = bc.inject_components(target, dry_run=False)
    assert changed is True

    lines = target.read_text(encoding="utf-8").splitlines()
    assert "  <!-- COMPONENT:nav -->" in lines
    assert "  <nav class=\"site-nav\">" in lines
    assert "  <ul><li>Archive</li></ul>" in lines
    assert "  </nav>" in lines
    assert "  <!-- /COMPONENT:nav -->" in lines


def test_wave_bg_empty_block_keeps_indent(monkeypatch, tmp_path: Path):
    website = tmp_path / "website"
    components = website / "_components"
    target = website / "archive" / "index.html"
    components.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)

    target.write_text(
        "\n".join(
            [
                "<main>",
                "    <!-- COMPONENT:wave-bg -->",
                "    <div class=\"wave-bg\">legacy</div>",
                "    <!-- /COMPONENT:wave-bg -->",
                "</main>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(bc, "WEBSITE_DIR", website)
    monkeypatch.setattr(bc, "COMPONENTS_DIR", components)
    monkeypatch.setattr(bc, "PROJECT_ROOT", tmp_path)

    changed = bc.inject_components(target, dry_run=False)
    assert changed is True
    lines = target.read_text(encoding="utf-8").splitlines()
    assert "    <!-- COMPONENT:wave-bg -->" in lines
    assert "    <!-- /COMPONENT:wave-bg -->" in lines
    assert "legacy" not in target.read_text(encoding="utf-8")
