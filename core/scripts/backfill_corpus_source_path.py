#!/usr/bin/env python3
"""
Backfill missing `source_path` in corpus entry files.

Policy:
- If `source_path` is empty, set canonical path:
  knowledge/signals/{signal_id}.json
- Keep updates deterministic and idempotent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENTRIES_DIR = PROJECT_ROOT / "knowledge" / "corpus" / "entries"
SIGNALS_DIR = PROJECT_ROOT / "knowledge" / "signals"


def canonical_source_path(signal_id: str) -> str:
    return f"knowledge/signals/{signal_id}.json"


def run(write: bool) -> int:
    updated = 0
    already_ok = 0
    malformed = 0
    source_file_exists = 0
    source_file_missing = 0

    for entry_path in sorted(ENTRIES_DIR.glob("entry_*.json")):
        try:
            entry = json.loads(entry_path.read_text(encoding="utf-8"))
        except Exception:
            malformed += 1
            continue

        source_path = str(entry.get("source_path") or "").strip()
        signal_id = str(entry.get("signal_id") or "").strip()
        if source_path:
            already_ok += 1
            continue
        if not signal_id:
            malformed += 1
            continue

        new_source_path = canonical_source_path(signal_id)
        if write:
            entry["source_path"] = new_source_path
            entry_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")

        updated += 1
        if (SIGNALS_DIR / f"{signal_id}.json").exists():
            source_file_exists += 1
        else:
            source_file_missing += 1

    summary = {
        "entries_dir": str(ENTRIES_DIR),
        "write": write,
        "updated": updated,
        "already_ok": already_ok,
        "malformed": malformed,
        "source_file_exists": source_file_exists,
        "source_file_missing": source_file_missing,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill corpus entry source_path")
    parser.add_argument("--write", action="store_true", help="write updates to files")
    args = parser.parse_args()
    return run(write=args.write)


if __name__ == "__main__":
    raise SystemExit(main())

