#!/usr/bin/env python3
"""
build.py — LAYER OS 통합 빌드 파이프라인

사용법:
    python build.py              # 전체: archive → components → cache bust
    python build.py --components # 컴포넌트만
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

# 캐시 버스팅 대상: CSS 참조가 있는 HTML 파일
CACHE_BUST_PATTERN = re.compile(r'(style\.css)\?v=[a-zA-Z0-9]+')


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
    parser.add_argument("--bust", action="store_true", help="캐시 버스팅만")
    parser.add_argument("--dry-run", action="store_true", help="변경 프리뷰")
    args = parser.parse_args()

    # 특정 단계만 실행
    run_all = not (args.archive or args.components or args.bust)

    logger.info("═══ LAYER OS Build Pipeline ═══")

    # 1. Archive (에세이 생성)
    if run_all or args.archive:
        run_script("build_archive.py", dry_run=args.dry_run)

    # 2. Components (nav/footer/wave-bg 주입)
    if run_all or args.components:
        run_script("build_components.py", dry_run=args.dry_run)

    # 3. Cache Busting
    if run_all or args.bust:
        logger.info("─── cache bust ───")
        bust_cache(dry_run=args.dry_run)

    logger.info("═══ Build Complete ═══")


if __name__ == "__main__":
    main()
