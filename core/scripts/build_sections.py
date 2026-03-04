#!/usr/bin/env python3
"""섹션 페이지 빌더 — Jinja2 템플릿 기반 조립.

archive / practice / lab index.html 을 _templates/section-page.html 로
조립한다. 조립 후 build_components.py 가 COMPONENT 마커를 주입한다.

Usage:
    python3 core/scripts/build_sections.py
"""
import hashlib
import json
import os
import sys

from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader
    JINJA_AVAILABLE = True
except ImportError:
    Environment = None
    FileSystemLoader = None
    JINJA_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "website"
TMPL_DIR = WEB / "_templates"
PAGES_DIR = WEB / "_pages"

# JS 해시 계산
_js_path = WEB / "assets" / "js" / "site.js"
_js_hash = hashlib.md5(_js_path.read_bytes()).hexdigest()[:8] if _js_path.exists() else "00000000"

# 페이지 → 출력 경로 맵
PAGE_MAP = {
    "archive": WEB / "archive" / "index.html",
    "practice": WEB / "practice" / "index.html",
    "lab": WEB / "lab" / "index.html",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def build_page(page_id: str, out_path: Path) -> None:
    page_dir = PAGES_DIR / page_id
    meta = json.loads(_read(page_dir / "meta.json"))

    controls_struct = meta.get("controls")
    controls = None if controls_struct else (_read(page_dir / "controls.html").strip() or None)
    body = _read(page_dir / "body.html")
    page_script = _read(page_dir / "script.html").strip() or None

    env = Environment(loader=FileSystemLoader(str(TMPL_DIR)), autoescape=False)
    tmpl = env.get_template("section-page.html")

    rendered = tmpl.render(
        title=meta["title"],
        description=meta["description"],
        og_url=meta["og_url"],
        body_class=meta["body_class"],
        preamble=meta["preamble"],
        controls_struct=controls_struct,
        controls=controls,
        body=body,
        page_script=page_script,
        js_hash=_js_hash,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"빌드: {out_path.relative_to(ROOT)}")


def main() -> None:
    print("─── section pages ───")
    if not JINJA_AVAILABLE:
        missing = [p for p in PAGE_MAP.values() if not p.exists()]
        if missing:
            print("jinja2 없음 — pip3 install jinja2")
            for path in missing:
                print(f"누락: {path.relative_to(ROOT)}")
            sys.exit(1)
        print("jinja2 없음 — 기존 section 페이지 유지(스킵)")
        return

    for page_id, out_path in PAGE_MAP.items():
        build_page(page_id, out_path)


if __name__ == "__main__":
    main()
