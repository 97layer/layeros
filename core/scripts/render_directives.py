#!/usr/bin/env python3
"""
practice.md 역할 섹션 슬라이스 유틸

사용법:
  python3 core/scripts/render_directives.py --agent CE
  python3 core/scripts/render_directives.py --section II-10 --max-chars 4000
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.system.directive_loader import load_section


DEFAULT_SECTIONS = {
    "AD": "I-10",
    "CE": "II-11",
    "SA": "II-10",
}


def render(agent: Optional[str], section: Optional[str], max_chars: int) -> str:
    sec = section or DEFAULT_SECTIONS.get(agent.upper() if agent else "")
    if not sec:
        raise SystemExit("section을 지정하거나 지원되는 agent(AD/CE/SA)를 선택하세요.")
    return load_section("practice.md", sec, max_chars=max_chars)


def main():
    parser = argparse.ArgumentParser(description="practice.md 섹션 추출")
    parser.add_argument("--agent", choices=["AD", "CE", "SA"], help="에이전트 키")
    parser.add_argument("--section", help="섹션 ID 예: I-10, II-10, II-11")
    parser.add_argument("--max-chars", type=int, default=3000, help="최대 출력 길이")
    args = parser.parse_args()

    text = render(args.agent, args.section, args.max_chars)
    print(text)


if __name__ == "__main__":
    main()
