#!/usr/bin/env python3
"""
Regenerate sitemap and stamp system_state metadata.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYSTEM_STATE_PATH = PROJECT_ROOT / "knowledge" / "system" / "system_state.json"
sys.path.insert(0, str(PROJECT_ROOT))

from core.scripts.build_archive import SITEMAP_FILE, build_sitemap


def stamp_system_state() -> None:
    if not SYSTEM_STATE_PATH.exists():
        return
    try:
        payload = json.loads(SYSTEM_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    now_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload["sitemap_status"] = "UPDATED"
    payload["sitemap_last_updated"] = now_local
    payload["last_update"] = now_local

    tmp = SYSTEM_STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SYSTEM_STATE_PATH)


def main() -> int:
    build_sitemap()
    stamp_system_state()
    print(str(SITEMAP_FILE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
