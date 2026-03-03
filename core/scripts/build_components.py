#!/usr/bin/env python3
"""
build_components.py — LAYER OS 컴포넌트 빌드 스크립트

마커 주석 사이의 HTML을 표준 프래그먼트로 교체한다.
마커: <!-- COMPONENT:name -->...<!-- /COMPONENT:name -->

사용법:
    python build_components.py              # 전체 주입
    python build_components.py --dry-run    # 변경 프리뷰
    python build_components.py --init       # 최초: 마커 자동 삽입
    python build_components.py --file X     # 단일 파일
"""

import argparse
import logging
import os
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEBSITE_DIR = PROJECT_ROOT / "website"
COMPONENTS_DIR = WEBSITE_DIR / "_components"

# 제외 디렉토리/파일
EXCLUDE_DIRS = {"_components", "_templates"}
EXCLUDE_FILES = {"404.html"}

# 페이지별 footer 매핑: 어느 섹션이 어떤 footer를 쓰는지
FOOTER_CONTACT_SECTIONS = {"", "practice", "about", "woosunho"}
FOOTER_ARCHIVE_SECTIONS = {"archive"}

# 마커 패턴
MARKER_RE = re.compile(
    r"<!-- COMPONENT:(\w[\w-]*) -->.*?<!-- /COMPONENT:\1 -->",
    re.DOTALL,
)


def load_component(name: str) -> str:
    """_components/에서 프래그먼트 로드."""
    path = COMPONENTS_DIR / f"{name}.html"
    if not path.exists():
        logger.warning("컴포넌트 없음: %s", path)
        return ""
    return path.read_text(encoding="utf-8").strip()


def get_section(filepath: Path) -> str:
    """파일의 섹션(최상위 디렉토리) 반환. 루트면 빈 문자열."""
    rel = filepath.relative_to(WEBSITE_DIR)
    parts = rel.parts
    if len(parts) <= 1:
        return ""
    return parts[0]


def get_footer_type(filepath: Path) -> str:
    """페이지에 맞는 footer 타입 반환."""
    section = get_section(filepath)
    if section in FOOTER_ARCHIVE_SECTIONS:
        return "footer-archive"
    return "footer-contact"


def should_have_wave_bg(filepath: Path) -> bool:
    """wave-bg 포함 여부. 아카이브 에세이는 자체 canvas 사용."""
    section = get_section(filepath)
    if section == "archive":
        # archive/index.html은 wave-bg 없음, 에세이도 없음
        return False
    return True


def get_target_files(specific_file: str = None) -> list:
    """처리 대상 HTML 파일 목록."""
    if specific_file:
        p = Path(specific_file).resolve()
        if not p.exists():
            logger.error("파일 없음: %s", p)
            return []
        return [p]

    files = []
    for html_file in sorted(WEBSITE_DIR.rglob("*.html")):
        rel = html_file.relative_to(WEBSITE_DIR)
        parts = rel.parts

        # 제외 디렉토리
        if parts[0] in EXCLUDE_DIRS:
            continue
        # 제외 파일
        if rel.name in EXCLUDE_FILES:
            continue
        # proto_*.html 등 프로토타입 제외
        if rel.name.startswith("proto"):
            continue
        # _gen- 접두사 제외
        if rel.name.startswith("_gen"):
            continue

        files.append(html_file)

    return files


# ──────────────────────────────────────────────
# --init 모드: 기존 HTML에서 nav/footer/wave-bg 감지 → 마커로 래핑
# ──────────────────────────────────────────────

def init_markers(filepath: Path, dry_run: bool = False) -> bool:
    """기존 nav/footer/wave-bg를 마커로 래핑. 이미 마커가 있으면 건너뜀."""
    content = filepath.read_text(encoding="utf-8")
    original = content
    changed = False

    # 이미 마커가 있으면 건너뜀
    if "<!-- COMPONENT:nav -->" in content:
        return False

    # --- NAV 마커 삽입 ---
    # Pattern A: <nav class="site-nav"...>...</nav> + <div class="nav-overlay"...>...</div>
    nav_pattern_a = re.compile(
        r'(<nav\s+class="site-nav"[^>]*>.*?</nav>\s*'
        r'<div\s+class="nav-overlay"[^>]*>.*?</div>)',
        re.DOTALL,
    )
    # Pattern B: <nav class="site-nav"...>...</nav> (overlay 없음)
    nav_pattern_b = re.compile(
        r'(<nav\s+class="site-nav"[^>]*>.*?</nav>)',
        re.DOTALL,
    )
    # Pattern C (에세이): bare <nav>...</nav>
    nav_pattern_c = re.compile(
        r'(<nav>\s*<a\s+href="[^"]*"\s+class="nav-logo">.*?</nav>)',
        re.DOTALL,
    )

    for pattern in [nav_pattern_a, nav_pattern_b, nav_pattern_c]:
        m = pattern.search(content)
        if m:
            old = m.group(0)
            wrapped = "<!-- COMPONENT:nav -->\n" + old + "\n<!-- /COMPONENT:nav -->"
            content = content.replace(old, wrapped, 1)
            changed = True
            break

    # --- WAVE-BG 마커 삽입 ---
    # wave-bg div (여러 줄, 중복 주석 포함)
    wave_pattern = re.compile(
        r'((?:<!-- wave-bg[^>]*-->\s*)?'
        r'<div\s[^>]*class="wave-bg"[^>]*>.*?</div>)'
        r'(\s*(?:<!-- wave-bg[^>]*-->\s*)*)',
        re.DOTALL,
    )
    m = wave_pattern.search(content)
    if m:
        # 전체 매치 (wave-bg div + 후행 주석들)
        full_match = m.group(0)
        wrapped = "<!-- COMPONENT:wave-bg -->\n" + full_match.strip() + "\n<!-- /COMPONENT:wave-bg -->"
        content = content.replace(full_match, wrapped, 1)
        changed = True

    # --- FOOTER 마커 삽입 ---
    # 모든 footer 패턴: <footer class="site-footer">...</footer> 또는 <footer class="section--light">...</footer>
    footer_pattern = re.compile(
        r'(<footer\s+class="(?:site-footer|section--light)"[^>]*>.*?</footer>)',
        re.DOTALL,
    )
    m = footer_pattern.search(content)
    if m:
        old = m.group(0)
        wrapped = "<!-- COMPONENT:footer -->\n" + old + "\n<!-- /COMPONENT:footer -->"
        content = content.replace(old, wrapped, 1)
        changed = True

    if changed and content != original:
        if dry_run:
            logger.info("[DRY-RUN] 마커 삽입: %s", filepath.relative_to(PROJECT_ROOT))
        else:
            filepath.write_text(content, encoding="utf-8")
            logger.info("마커 삽입: %s", filepath.relative_to(PROJECT_ROOT))
        return True
    return False


# ──────────────────────────────────────────────
# 주입 모드: 마커 사이 교체
# ──────────────────────────────────────────────

def inject_components(filepath: Path, dry_run: bool = False) -> bool:
    """마커 사이의 내용을 표준 컴포넌트로 교체."""
    content = filepath.read_text(encoding="utf-8")
    original = content

    def replace_marker(match):
        name = match.group(1)
        if name == "nav":
            fragment = load_component("nav")
        elif name == "footer":
            footer_type = get_footer_type(filepath)
            fragment = load_component(footer_type)
        elif name == "wave-bg":
            if should_have_wave_bg(filepath):
                fragment = load_component("wave-bg")
            else:
                # wave-bg가 필요 없는 페이지면 마커만 유지, 내부 비움
                return "<!-- COMPONENT:wave-bg -->\n<!-- /COMPONENT:wave-bg -->"
        else:
            fragment = load_component(name)

        if not fragment:
            return match.group(0)

        return f"<!-- COMPONENT:{name} -->\n{fragment}\n<!-- /COMPONENT:{name} -->"

    content = MARKER_RE.sub(replace_marker, content)

    if content != original:
        if dry_run:
            logger.info("[DRY-RUN] 주입: %s", filepath.relative_to(PROJECT_ROOT))
        else:
            filepath.write_text(content, encoding="utf-8")
            logger.info("주입: %s", filepath.relative_to(PROJECT_ROOT))
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="LAYER OS 컴포넌트 빌드")
    parser.add_argument("--init", action="store_true", help="최초 마커 삽입")
    parser.add_argument("--dry-run", action="store_true", help="변경 프리뷰")
    parser.add_argument("--file", type=str, help="단일 파일 처리")
    args = parser.parse_args()

    files = get_target_files(args.file)
    if not files:
        logger.error("처리할 파일 없음")
        sys.exit(1)

    logger.info("대상: %d 파일", len(files))

    count = 0
    if args.init:
        for f in files:
            if init_markers(f, dry_run=args.dry_run):
                count += 1
        logger.info("마커 삽입: %d 파일", count)
    else:
        for f in files:
            if inject_components(f, dry_run=args.dry_run):
                count += 1
        logger.info("주입: %d 파일", count)


if __name__ == "__main__":
    main()
