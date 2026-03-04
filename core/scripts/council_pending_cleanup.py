#!/usr/bin/env python3
"""
Council pending cleanup
- 처리 완료된 proposal(council_approve/reject, council_room 결정 로그)를
  .infra/council 에서 정리한다.
"""

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.system.council_manager import CouncilManager


def main():
    parser = argparse.ArgumentParser(description="Cleanup processed council proposals")
    parser.add_argument("--dry-run", action="store_true", help="삭제 없이 대상만 출력")
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON 형식 출력")
    args = parser.parse_args()

    result = CouncilManager().reconcile_pending_proposals(dry_run=args.dry_run)
    result["dry_run"] = args.dry_run

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False))
        return

    action = "would_delete" if args.dry_run else "deleted"
    print(f"{action}={len(result['deleted'])}")
    if result["deleted"]:
        print(",".join(result["deleted"]))
    print(f"remaining_pending={len(result['skipped'])}")
    if result["skipped"]:
        print(",".join(result["skipped"]))


if __name__ == "__main__":
    main()
