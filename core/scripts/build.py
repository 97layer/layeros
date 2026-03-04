#!/usr/bin/env python3
"""
build.py — LAYER OS 통합 빌드 파이프라인

사용법:
    python build.py              # 전체: archive → components → easter → cache bust
    python build.py --components # 컴포넌트만
    python build.py --easter     # about 이스터에그 타임스탬프+수치만
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
SITE_JS = WEBSITE_DIR / "assets" / "js" / "site.js"
MAIN_JS = WEBSITE_DIR / "assets" / "js" / "main.js"
ABOUT_HTML = WEBSITE_DIR / "about" / "index.html"

# 캐시 버스팅 대상: CSS/JS 참조가 있는 HTML 파일
CACHE_BUST_PATTERN = re.compile(r'(style\.css)\?v=[a-zA-Z0-9]+')
CACHE_BUST_JS_PATTERN = re.compile(r'(site\.js)\?v=[a-zA-Z0-9]+')
CACHE_BUST_MAINJS_PATTERN = re.compile(r'(main\.js)\?v=[a-zA-Z0-9]+')

# about 이스터에그 블록 마커
EASTER_RE = re.compile(r'<!-- EASTER:START -->.*?<!-- EASTER:END -->', re.DOTALL)

EASTER_MSGS = [
    "글을 {commits:,}번 고쳤습니다. {deletions:,}줄이 사라졌습니다.",
    "디렉터가 밤낮없이 수정하고 있습니다.",
    "지운 것이 남은 것보다 많습니다.",
    "비워야 보인다고 믿습니다. — 97layer",
]


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


def get_js_hash() -> str:
    """site.js의 짧은 해시 생성."""
    if not SITE_JS.exists():
        return "0"
    content = SITE_JS.read_bytes()
    return hashlib.md5(content).hexdigest()[:8]


def get_mainjs_hash() -> str:
    """main.js의 짧은 해시 생성."""
    if not MAIN_JS.exists():
        return "0"
    content = MAIN_JS.read_bytes()
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


def _get_git_timestamps(n: int) -> list:
    """git log에서 균등 분포 타임스탬프 n개 추출 (최신→구버전 순)."""
    try:
        r = subprocess.run(
            ["git", "log", "--format=%ad", "--date=format:%Y.%m.%d %H:%M"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=30,
        )
        ts = [t.strip() for t in r.stdout.splitlines() if t.strip()]
        if not ts:
            return ["——"] * n
        total = len(ts)
        indices = [int(i * (total - 1) / max(n - 1, 1)) for i in range(n)]
        return [ts[i] for i in indices]
    except Exception as e:
        logger.warning("타임스탬프 추출 실패: %s", e)
        return ["——"] * n


def inject_easter_log(dry_run: bool = False) -> bool:
    """about 이스터에그 — git 타임스탬프 + stats 빌드 시 주입."""
    if not ABOUT_HTML.exists():
        logger.warning("about/index.html 없음")
        return False

    commits, deletions = compute_site_stats()
    timestamps = _get_git_timestamps(len(EASTER_MSGS))

    lines = []
    for ts, msg in zip(timestamps, EASTER_MSGS):
        text = msg.format(commits=commits, deletions=deletions)
        lines.append('    <span class="elog"><time>{}</time>{}</span>'.format(ts, text))

    inner = "\n".join(lines)
    block = "<!-- EASTER:START -->\n{}\n    <!-- EASTER:END -->".format(inner)

    content = ABOUT_HTML.read_text(encoding="utf-8")
    updated = EASTER_RE.sub(block, content)

    if updated == content:
        logger.info("easter log 변경 없음")
        return True

    if dry_run:
        logger.info("[DRY-RUN] easter log:\n%s", inner)
    else:
        ABOUT_HTML.write_text(updated, encoding="utf-8")
        logger.info("easter log 갱신: commits=%d, deletions=%d", commits, deletions)
    return True


def bust_cache(dry_run: bool = False) -> int:
    """전 HTML 파일의 style.css?v=xxx + site.js?v=xxx를 현재 해시로 교체."""
    css_hash = get_css_hash()
    js_hash = get_js_hash()
    mainjs_hash = get_mainjs_hash()
    new_css_ref = f"style.css?v={css_hash}"
    new_js_ref = f"site.js?v={js_hash}"
    new_mainjs_ref = f"main.js?v={mainjs_hash}"
    count = 0

    for html_file in sorted(WEBSITE_DIR.rglob("*.html")):
        # _components/, _templates/ 제외
        rel = html_file.relative_to(WEBSITE_DIR)
        if rel.parts[0] in ("_components", "_templates"):
            continue

        content = html_file.read_text(encoding="utf-8")
        updated = CACHE_BUST_PATTERN.sub(new_css_ref, content)
        updated = CACHE_BUST_JS_PATTERN.sub(new_js_ref, updated)
        updated = CACHE_BUST_MAINJS_PATTERN.sub(new_mainjs_ref, updated)

        if updated != content:
            count += 1
            if dry_run:
                logger.info("[DRY-RUN] 캐시 버스트: %s", rel)
            else:
                html_file.write_text(updated, encoding="utf-8")
                logger.info("캐시 버스트: %s", rel)

    logger.info("캐시 버스트: %d 파일 (css=%s, js=%s, main=%s)", count, css_hash, js_hash, mainjs_hash)
    return count




def main():
    parser = argparse.ArgumentParser(description="LAYER OS 통합 빌드")
    parser.add_argument("--archive", action="store_true", help="아카이브만 빌드")
    parser.add_argument("--sections", action="store_true", help="섹션 페이지만 빌드 (archive/practice/lab index)")
    parser.add_argument("--components", action="store_true", help="컴포넌트만 주입")
    parser.add_argument("--easter", action="store_true", help="about 이스터에그 타임스탬프+수치 갱신")
    parser.add_argument("--bust", action="store_true", help="캐시 버스팅만")
    parser.add_argument("--dry-run", action="store_true", help="변경 프리뷰")
    args = parser.parse_args()

    # 특정 단계만 실행
    run_all = not (args.archive or args.sections or args.components or args.easter or args.bust)

    logger.info("═══ LAYER OS Build Pipeline ═══")
    failures = []

    # 1. Archive (에세이 생성)
    if run_all or args.archive:
        if not run_script("build_archive.py", dry_run=args.dry_run):
            failures.append("build_archive.py")

    # 2. Section Pages (archive / practice / lab Jinja2 조립)
    if run_all or args.sections or args.components:
        if not run_script("build_sections.py", dry_run=args.dry_run):
            failures.append("build_sections.py")

    # 3. Components (nav/footer/head 주입)
    if run_all or args.components:
        if not run_script("build_components.py", dry_run=args.dry_run):
            failures.append("build_components.py")

    # 3. Easter Log (about 이스터에그 타임스탬프+수치 갱신)
    if run_all or args.easter:
        logger.info("─── easter log ───")
        if not inject_easter_log(dry_run=args.dry_run):
            failures.append("inject_easter_log")

    # 4. Cache Busting
    if run_all or args.bust:
        logger.info("─── cache bust ───")
        bust_cache(dry_run=args.dry_run)

    if failures:
        logger.error("❌ Build failed: %s", ", ".join(failures))
        sys.exit(1)

    logger.info("═══ Build Complete ═══")


if __name__ == "__main__":
    main()
