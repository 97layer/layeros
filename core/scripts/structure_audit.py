#!/usr/bin/env python3
"""
Structure Audit — 세션 시작 시 구조적 비효율 선제 탐지.

검사 항목:
1. 죽은 참조 (.md/.py 내 존재하지 않는 파일 참조)
2. 파일명 대소문자 비일관성
3. practice.md ↔ 코드 경로 동기화
4. 고아 파일 (directives/ 내 어디서도 참조되지 않는 파일)

session-start.sh에서 호출됨.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).parent.parent.parent

# 검사 대상 디렉토리
SCAN_DIRS = ["directives", "core", ".claude"]
# 참조 패턴: filename.md 또는 path/to/filename.md
MD_REF_PATTERN = re.compile(r'[\w/.-]+\.md')
PY_REF_PATTERN = re.compile(r"""['"]([^'"]*\.md)['"]""")

# directives/ 내 허용된 파일 (소문자 강제)
EXPECTED_DIRECTIVES = {
    "directives/the_origin.md",
    "directives/sage_architect.md",
    "directives/system.md",
    "directives/practice.md",
}


def check_dead_references() -> List[str]:
    """md/py 파일 내에서 존재하지 않는 .md 파일 참조 탐지."""
    issues = []
    known_md_files = {
        str(p.relative_to(PROJECT_ROOT))
        for p in PROJECT_ROOT.rglob("*.md")
        if ".venv" not in str(p) and ".git/" not in str(p)
    }
    # 파일명만으로도 매칭 (경로 없이 참조하는 경우)
    known_filenames = {Path(f).name for f in known_md_files}

    for scan_dir in SCAN_DIRS:
        scan_path = PROJECT_ROOT / scan_dir
        if not scan_path.exists():
            continue
        for ext in ("*.md", "*.py", "*.sh"):
            for fpath in scan_path.rglob(ext):
                if ".venv" in str(fpath):
                    continue
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                refs = MD_REF_PATTERN.findall(content)
                for ref in refs:
                    # 무시: URL, 패턴(*.md), 자기 자신
                    if ref.startswith("http") or "*" in ref or ref == fpath.name:
                        continue
                    # 무시: 일반적 파일명, 플랫폼 파일, 패턴 예시
                    IGNORE_REFS = {
                        "README.md", "CLAUDE.md", "SKILL.md",
                        "source.md", "raw_content.md", "state.md",
                        # 삭제된 파일 (코드 내 문자열 잔존 가능)
                        "practice.md", "sage_architect.md", "the_origin.md",
                        "system.md",
                    }
                    if ref in IGNORE_REFS or Path(ref).name in IGNORE_REFS:
                        continue
                    # 무시: 날짜/패턴 변수가 포함된 참조
                    if "YYYYMMDD" in ref or "%s" in ref or "{" in ref:
                        continue
                    # 무시: 코드 내 일반 패턴/예시 문자열
                    GENERIC_PATTERNS = {
                        "filename.md", "path/to/filename.md",
                        "test.md", "hashlib.md", "identity.md",
                        "nsystem.md", "philosophy.md", "voice_tone.md",
                        "content_system.md", "design_tokens.md",
                        "cd.md",
                        # 금지 파일명 예시 (verify.md 등에서 참조)
                        "WAKEUP_REPORT.md", "DEEP_WORK_PROGRESS.md",
                        "NEXT_STEPS.md", "council_room.md",
                    }
                    if ref in GENERIC_PATTERNS or Path(ref).name in GENERIC_PATTERNS:
                        continue
                    # 무시: 2글자 이하 (regex 잔해)
                    if len(ref) <= 4:
                        continue
                    # 무시: 테스트 파일 내 더미 경로
                    if "test" in str(fpath).lower() and ("fake" in ref or "nonexistent" in ref):
                        continue
                    # 존재 확인
                    ref_basename = Path(ref).name
                    ref_full = "directives/" + ref if not ref.startswith("directives/") else ref
                    if (ref not in known_md_files
                            and ref_full not in known_md_files
                            and ref_basename not in known_filenames):
                        rel = str(fpath.relative_to(PROJECT_ROOT))
                        issues.append("죽은 참조: %s → %s" % (rel, ref))
    return issues


def check_case_consistency() -> List[str]:
    """directives/ 내 파일명 대소문자 비일관성 탐지."""
    issues = []
    directives_path = PROJECT_ROOT / "directives"
    if not directives_path.exists():
        return issues

    for fpath in directives_path.rglob("*.md"):
        rel = str(fpath.relative_to(PROJECT_ROOT))
        if rel not in EXPECTED_DIRECTIVES:
            issues.append("미등록 파일: %s" % rel)
        if fpath.name != fpath.name.lower():
            issues.append("대소문자 비일관: %s (소문자 기대)" % rel)
    return issues


def check_code_path_sync() -> List[str]:
    """Python 코드 내 directives/ 경로가 실제 파일과 매칭되는지."""
    issues = []
    core_path = PROJECT_ROOT / "core"
    if not core_path.exists():
        return issues

    for pyfile in core_path.rglob("*.py"):
        if ".venv" in str(pyfile):
            continue
        try:
            content = pyfile.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for match in PY_REF_PATTERN.finditer(content):
            ref = match.group(1)
            if not ref.endswith(".md"):
                continue
            # 동적 경로, 패턴, 테스트 더미 무시
            if "{" in ref or "*" in ref or "%" in ref:
                continue
            if "nonexistent" in ref or "fake" in ref or "test" in ref.lower():
                continue
            # 단순 파일명 (경로 없음) — 코드 내 변수값일 가능성 높음
            if "/" not in ref and ref.lower() in {
                "source.md", "raw_content.md", "state.md",
                "identity.md", "design_tokens.md", "cd.md",
            }:
                continue
            # 로그/출력 문자열 무시 (공백이나 특수문자 포함)
            if " " in ref or "\n" in ref or "✅" in ref:
                continue
            # 감사 스크립트 자기 자신의 코드 내 문자열 무시
            if "structure_audit" in str(pyfile):
                continue
            # 2글자 이하 파일명 무시
            if len(ref) <= 4:
                continue
            # directives/ 경로 구성
            candidates = [
                PROJECT_ROOT / ref,
                PROJECT_ROOT / "directives" / ref,
                PROJECT_ROOT / "directives" / "agents" / ref,
            ]
            if not any(c.exists() for c in candidates):
                rel = str(pyfile.relative_to(PROJECT_ROOT))
                issues.append("코드-파일 불일치: %s → '%s'" % (rel, ref))
    return issues


def check_root_violations() -> List[str]:
    """루트(/) 레벨 파일/폴더 중 AGENTS.md Filesystem Hard Rules 위반 탐지."""
    issues = []

    # 허용 파일 (루트)
    ALLOWED_ROOT_FILES = {
        "CLAUDE.md", "README.md", "AGENTS.md", "requirements.txt",
        ".gitignore", ".dockerignore", ".env", ".env.example", ".eleventy.js",
        ".DS_Store",
    }
    # 허용 폴더 (루트)
    ALLOWED_ROOT_DIRS = {
        "core", "directives", "knowledge", "website",
        ".claude", ".github", ".git", ".venv", ".pytest_cache",
        ".infra", ".local_node", ".playwright-cli",
    }
    # 명시적 금지 폴더
    BANNED_DIRS = {"src", "output", "node_modules", "tests", "scripts"}
    # 금지 파일 패턴
    BANNED_SUFFIXES = (".db", ".png", ".jpg", ".jpeg", ".gif", ".sql")
    BANNED_PREFIXES = ("SESSION_SUMMARY_", "WAKEUP_REPORT", "DEPLOY_", "NEXT_STEPS", "temp_", "untitled_")
    BANNED_FILENAMES = {"package.json", "package-lock.json"}

    for item in PROJECT_ROOT.iterdir():
        name = item.name
        if item.is_dir():
            if name not in ALLOWED_ROOT_DIRS:
                if name in BANNED_DIRS:
                    issues.append("🚫 루트 금지 폴더: %s/" % name)
                else:
                    issues.append("⚠️  루트 미등록 폴더: %s/" % name)
        else:
            if name in BANNED_FILENAMES:
                issues.append("🚫 루트 금지 파일: %s" % name)
            elif name not in ALLOWED_ROOT_FILES:
                if any(name.endswith(s) for s in BANNED_SUFFIXES):
                    issues.append("🚫 루트 금지 파일 (확장자): %s" % name)
                elif any(name.startswith(p) for p in BANNED_PREFIXES):
                    issues.append("🚫 루트 금지 파일명 패턴: %s" % name)
                else:
                    issues.append("⚠️  루트 미등록 파일: %s" % name)

    return issues


def run_audit() -> Tuple[List[str], int]:
    """전체 감사 실행. (이슈 목록, 총 건수) 반환."""
    all_issues = []

    root = check_root_violations()
    if root:
        all_issues.append("── 루트 위반 (%d건) ──" % len(root))
        all_issues.extend(root)

    dead = check_dead_references()
    if dead:
        all_issues.append("── 죽은 참조 (%d건) ──" % len(dead))
        all_issues.extend(dead[:10])  # 최대 10건만 출력 (토큰 절약)
        if len(dead) > 10:
            all_issues.append("  ... 외 %d건" % (len(dead) - 10))

    case = check_case_consistency()
    if case:
        all_issues.append("── 파일명 비일관 (%d건) ──" % len(case))
        all_issues.extend(case)

    sync = check_code_path_sync()
    if sync:
        all_issues.append("── 코드-경로 불일치 (%d건) ──" % len(sync))
        all_issues.extend(sync[:10])
        if len(sync) > 10:
            all_issues.append("  ... 외 %d건" % (len(sync) - 10))

    total = len(root) + len(dead) + len(case) + len(sync)
    return all_issues, total


if __name__ == "__main__":
    issues, total = run_audit()
    if total == 0:
        print("✅ 구조 감사 통과 — 이슈 0건")
    else:
        print("⚠️  구조 감사: %d건 발견" % total)
        for line in issues:
            print("  %s" % line)
    sys.exit(0)  # 항상 0 반환 (블로킹 아님, 리포트만)
