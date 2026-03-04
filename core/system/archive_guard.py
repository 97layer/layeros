"""
Archive layout and tone guard.

Rules:
- Layout: archive/index.html must contain ledger structure and must not contain legacy components.
- Tone: all visible Korean sentences should end with 합니다체; flags known 한다체 endings.
Usage:
  python3 core/system/archive_guard.py
Exit code: 0 on pass, 1 on violation.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[2]
HTML_PATH = ROOT / "website" / "archive" / "index.html"

REQUIRED_MARKERS = [
    "archive-ledger",
    'id="archive-ledger"',
    "archive-stats",
    "mini-index",
]

FORBIDDEN_MARKERS = [
    "archive-cover",
    "archive-lane",
    "archive-tabs",
    "archive-list--strip",
    "table-toggle",
]

# Rough 어미 검출: 한다/했다/한다는 etc. (합니다체 아님)
BAN_ENDINGS = [
    r"한다\.",
    r"했다\.",
    r"한다고",
    r"한다면",
    r"한다니",
    r"한다는",
    r"한다며",
    r"한다면",
]


def load_html() -> str:
    return HTML_PATH.read_text(encoding="utf-8")


def check_required(html: str, report: List[str]) -> None:
    for mark in REQUIRED_MARKERS:
        if mark not in html:
            report.append(f"missing required marker: {mark}")


def check_forbidden(html: str, report: List[str]) -> None:
    for mark in FORBIDDEN_MARKERS:
        if mark in html:
            report.append(f"forbidden legacy marker present: {mark}")


def check_tone(html: str, report: List[str]) -> None:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    for pat in BAN_ENDINGS:
        m = re.search(pat, text)
        if m:
            report.append(f"tone warning: '{m.group(0)}' (해야 합니다체)")


def main() -> int:
    if not HTML_PATH.exists():
        print(f"missing {HTML_PATH}", file=sys.stderr)
        return 1
    html = load_html()
    report: List[str] = []
    check_required(html, report)
    check_forbidden(html, report)
    check_tone(html, report)
    if report:
        for line in report:
            print(f"[FAIL] {line}")
        return 1
    print("[PASS] archive_guard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
