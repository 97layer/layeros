#!/usr/bin/env python3
"""
directive_loader.py — 섹션 단위 디렉티브 로더.

에이전트가 문서 전체를 로드 후 truncate하는 대신,
Task Classification(A~E)에 따라 필요한 섹션만 정확히 추출한다.

사용법:
    from core.system.directive_loader import load_for_task, load_section

    # Task 유형별 자동 로딩
    context = load_for_task("A")  # 에세이 작성용 컨텍스트

    # 특정 섹션 직접 로딩
    section = load_section("sage_architect.md", "§10")
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DIRECTIVES_DIR = PROJECT_ROOT / "directives"

# ── Task Classification → 필요 섹션 매핑 (system.md §6) ──────────

TASK_SECTIONS: Dict[str, List[Dict[str, str]]] = {
    "A": [  # 에세이 작성
        {"file": "the_origin.md", "section": "프롤로그"},
        {"file": "sage_architect.md", "section": "§4"},
        {"file": "sage_architect.md", "section": "§5"},
        {"file": "sage_architect.md", "section": "§6"},
        {"file": "sage_architect.md", "section": "§9"},
        {"file": "practice.md", "section": "Part II"},
    ],
    "B": [  # 웹카피/DM
        {"file": "sage_architect.md", "section": "§7"},
        {"file": "sage_architect.md", "section": "§9"},
        {"file": "practice.md", "section": "II-8"},
    ],
    "C": [  # 시스템 문서 편집
        {"file": "sage_architect.md", "section": "§1"},
        {"file": "sage_architect.md", "section": "§9"},
    ],
    "D": [  # 디자인/시각
        {"file": "practice.md", "section": "Part I"},
        {"file": "sage_architect.md", "section": "§9"},
    ],
    "E": [  # 서비스 설계
        {"file": "practice.md", "section": "Part III"},
        {"file": "sage_architect.md", "section": "§3"},
    ],
}

# ── 에이전트별 기본 로딩 (슬롯 3) ────────────────────────────────

AGENT_SECTIONS: Dict[str, List[Dict[str, str]]] = {
    "SA": [
        {"file": "the_origin.md", "section": None},  # 브랜드 공명 필터 기준
        {"file": "sage_architect.md", "section": "§1"},
        {"file": "sage_architect.md", "section": "§9"},
        {"file": "practice.md", "section": "II-4"},
        {"file": "practice.md", "section": "II-5"},
        {"file": "practice.md", "section": "II-9"},
        {"file": "practice.md", "section": "II-10"},
    ],
    "CE": [
        {"file": "sage_architect.md", "section": "§4"},
        {"file": "sage_architect.md", "section": "§5"},
        {"file": "sage_architect.md", "section": "§6"},
        {"file": "sage_architect.md", "section": "§9"},
        {"file": "practice.md", "section": "Part II"},
        {"file": "practice.md", "section": "II-11"},
    ],
    "AD": [
        {"file": "sage_architect.md", "section": "§9"},
        {"file": "practice.md", "section": "Part I"},
        {"file": "practice.md", "section": "I-10"},
    ],
    "CD": [
        {"file": "sage_architect.md", "section": "§10"},
        {"file": "sage_architect.md", "section": "§9"},
    ],
}


def _read_file(filename: str) -> Optional[str]:
    """디렉티브 파일 읽기. 실패 시 None."""
    filepath = DIRECTIVES_DIR / filename
    try:
        return filepath.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("디렉티브 파일 없음: %s", filepath)
        return None
    except OSError as e:
        logger.error("디렉티브 읽기 실패: %s — %s", filepath, e)
        return None


def load_section(filename: str, section: Optional[str] = None,
                 max_chars: int = 3000) -> str:
    """
    특정 파일에서 섹션 추출.

    section 형식:
        - None: 파일 전체 (max_chars 제한)
        - "§N": ## N. 으로 시작하는 섹션
        - "Part I/II/III": # Part 으로 시작하는 대섹션
        - "II-4": ## II-4. 으로 시작하는 소섹션
        - "프롤로그": ## [프롤로그] 섹션
    """
    content = _read_file(filename)
    if content is None:
        return ""

    if section is None:
        return content[:max_chars]

    # §N 패턴 → "## N." 헤딩 찾기
    if section.startswith("§"):
        num = section[1:]
        pattern = re.compile(
            r"^## %s\.\s.*" % re.escape(num), re.MULTILINE
        )
    # Part I/II/III → "# Part" 헤딩
    elif section.startswith("Part "):
        part_name = section.replace("Part ", "")
        pattern = re.compile(
            r"^# Part %s\.\s.*" % re.escape(part_name), re.MULTILINE
        )
    # II-4 같은 소섹션 → "## II-4." 헤딩
    elif re.match(r"^[IVX]+-\d+$", section):
        pattern = re.compile(
            r"^## %s\.\s.*" % re.escape(section), re.MULTILINE
        )
    # 텍스트 매칭 (프롤로그 등)
    else:
        pattern = re.compile(
            r"^##?\s*\[?%s\]?.*" % re.escape(section), re.MULTILINE
        )

    match = pattern.search(content)
    if not match:
        logger.debug("섹션 미발견: %s/%s — 파일 앞부분 반환", filename, section)
        return content[:max_chars]

    start = match.start()

    # 같은 레벨 이상의 다음 헤딩까지 추출
    heading_level = content[start:start + 4].count("#")
    next_heading = re.compile(
        r"^#{1,%d}\s" % heading_level, re.MULTILINE
    )
    next_match = next_heading.search(content, match.end() + 1)
    end = next_match.start() if next_match else len(content)

    extracted = content[start:end].strip()
    if len(extracted) > max_chars:
        extracted = extracted[:max_chars] + "\n... (truncated)"

    return extracted


def load_for_task(task_type: str, max_total: int = 6000) -> str:
    """
    Task Classification에 따른 컨텍스트 자동 로딩.

    Args:
        task_type: "A"~"E" (system.md §6)
        max_total: 전체 출력 최대 문자 수

    Returns:
        연결된 컨텍스트 문자열
    """
    sections = TASK_SECTIONS.get(task_type.upper())
    if not sections:
        logger.warning("알 수 없는 Task 유형: %s", task_type)
        return ""

    parts = []
    total = 0
    for spec in sections:
        remaining = max_total - total
        if remaining <= 0:
            break
        text = load_section(spec["file"], spec["section"], max_chars=remaining)
        if text:
            parts.append(text)
            total += len(text)

    result = "\n\n---\n\n".join(parts)
    logger.info("Task %s 컨텍스트 로드: %d자 (%d 섹션)",
                task_type, len(result), len(parts))
    return result


def load_for_agent(agent_id: str, max_total: int = 6000) -> str:
    """
    에이전트별 기본 컨텍스트 로딩.

    Args:
        agent_id: "SA", "CE", "AD", "CD"
        max_total: 전체 출력 최대 문자 수
    """
    sections = AGENT_SECTIONS.get(agent_id.upper())
    if not sections:
        logger.warning("알 수 없는 에이전트: %s", agent_id)
        return ""

    parts = []
    total = 0
    for spec in sections:
        remaining = max_total - total
        if remaining <= 0:
            break
        text = load_section(spec["file"], spec["section"], max_chars=remaining)
        if text:
            parts.append(text)
            total += len(text)

    result = "\n\n---\n\n".join(parts)
    logger.info("Agent %s 컨텍스트 로드: %d자 (%d 섹션)",
                agent_id, len(result), len(parts))
    return result
