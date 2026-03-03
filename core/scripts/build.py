#!/usr/bin/env python3
"""
build.py — LAYER OS 통합 빌드 파이프라인

사용법:
    python build.py              # 전체: archive → components → stats → cache bust
    python build.py --components # 컴포넌트만
    python build.py --stats      # about 이스터에그 수치만
    python build.py --bust       # 캐시 버스팅만
    python build.py --dry-run    # 프리뷰
"""

import argparse
import hashlib
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEBSITE_DIR = PROJECT_ROOT / "website"
SCRIPTS_DIR = PROJECT_ROOT / "core" / "scripts"
STYLE_CSS = WEBSITE_DIR / "assets" / "css" / "style.css"
ABOUT_HTML = WEBSITE_DIR / "about" / "index.html"

# 캐시 버스팅 대상: CSS 참조가 있는 HTML 파일
CACHE_BUST_PATTERN = re.compile(r'(style\.css)\?v=[a-zA-Z0-9]+')

# about 이스터에그 수치 패턴
_STATS_RE = re.compile(r'글을 [\d,]+번 고쳤습니다\. [\d,]+줄이 사라졌습니다\.')


def run_script(name: str, args: list = None, dry_run: bool = False) -> bool:
    """서브 스크립트 실행."""
    script = SCRIPTS_DIR / name
    if not script.exists():
        logger.warning("스크립트 없음: %s", script)
        return False

    cmd = [sys.executable, str(script)]
    if args:
        cmd.extend(args)
    if dry_run:
        cmd.append("--dry-run")

    logger.info("─── %s ───", name)
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode == 0


def get_css_hash() -> str:
    """style.css의 짧은 해시 생성."""
    if not STYLE_CSS.exists():
        return "0"
    content = STYLE_CSS.read_bytes()
    return hashlib.md5(content).hexdigest()[:8]


def compute_site_stats() -> tuple:
    """git 기반 총 커밋 수 + 총 삭제 줄 수 반환."""
    commits = 0
    deletions = 0
    try:
        r = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=30,
        )
        if r.returncode == 0:
            commits = int(r.stdout.strip())
    except Exception as e:
        logger.warning("커밋 수 계산 실패: %s", e)

    try:
        r = subprocess.run(
            ["git", "log", "--numstat", "--format="],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=60,
        )
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[1].isdigit():
                deletions += int(parts[1])
    except Exception as e:
        logger.warning("삭제 줄 수 계산 실패: %s", e)

    return commits, deletions


def inject_site_stats(dry_run: bool = False) -> bool:
    """about/index.html 이스터에그 수치를 git 실제 데이터로 갱신."""
    if not ABOUT_HTML.exists():
        logger.warning("about/index.html 없음")
        return False

    commits, deletions = compute_site_stats()
    new_text = "글을 {:,}번 고쳤습니다. {:,}줄이 사라졌습니다.".format(commits, deletions)

    content = ABOUT_HTML.read_text(encoding="utf-8")
    updated = _STATS_RE.sub(new_text, content)

    if updated == content:
        logger.info("stats 변경 없음 (commits=%d, deletions=%d)", commits, deletions)
        return True

    if dry_run:
        logger.info("[DRY-RUN] stats: %s", new_text)
    else:
        ABOUT_HTML.write_text(updated, encoding="utf-8")
        logger.info("stats 갱신: %s", new_text)
    return True


def bust_cache(dry_run: bool = False) -> int:
    """전 HTML 파일의 style.css?v=xxx를 현재 CSS 해시로 교체."""
    css_hash = get_css_hash()
    new_ref = f"style.css?v={css_hash}"
    count = 0

    for html_file in sorted(WEBSITE_DIR.rglob("*.html")):
        # _components/, _templates/ 제외
        rel = html_file.relative_to(WEBSITE_DIR)
        if rel.parts[0] in ("_components", "_templates"):
            continue

        content = html_file.read_text(encoding="utf-8")
        updated = CACHE_BUST_PATTERN.sub(new_ref, content)

        if updated != content:
            count += 1
            if dry_run:
                logger.info("[DRY-RUN] 캐시 버스트: %s", rel)
            else:
                html_file.write_text(updated, encoding="utf-8")
                logger.info("캐시 버스트: %s", rel)

    logger.info("캐시 버스트: %d 파일 (v=%s)", count, css_hash)
    return count




def main():
    parser = argparse.ArgumentParser(description="LAYER OS 통합 빌드")
    parser.add_argument("--archive", action="store_true", help="아카이브만 빌드")
    parser.add_argument("--components", action="store_true", help="컴포넌트만 주입")
    parser.add_argument("--stats", action="store_true", help="about 이스터에그 수치만 갱신")
    parser.add_argument("--bust", action="store_true", help="캐시 버스팅만")
    parser.add_argument("--dry-run", action="store_true", help="변경 프리뷰")
    args = parser.parse_args()

    # 특정 단계만 실행
    run_all = not (args.archive or args.components or args.stats or args.bust)

    logger.info("═══ LAYER OS Build Pipeline ═══")

    # 1. Archive (에세이 생성)
    if run_all or args.archive:
        run_script("build_archive.py", dry_run=args.dry_run)

    # 2. Components (nav/footer/wave-bg 주입)
    if run_all or args.components:
        run_script("build_components.py", dry_run=args.dry_run)

    # 3. Site Stats (about 이스터에그 수치 갱신)
    if run_all or args.stats:
        logger.info("─── site stats ───")
        inject_site_stats(dry_run=args.dry_run)

    # 4. Cache Busting
    if run_all or args.bust:
        logger.info("─── cache bust ───")
        bust_cache(dry_run=args.dry_run)

    logger.info("═══ Build Complete ═══")


if __name__ == "__main__":
    main()
