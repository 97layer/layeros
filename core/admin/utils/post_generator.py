"""
Post Generator — 마크다운 → 정적 HTML 변환 + index.json 관리
_templates/article.html 기반 실제 템플릿 사용
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # LAYER OS root
WEBSITE_DIR = BASE_DIR / 'website'
ARCHIVE_DIR = WEBSITE_DIR / 'archive'
INDEX_PATH = ARCHIVE_DIR / 'index.json'
TEMPLATE_PATH = WEBSITE_DIR / '_templates' / 'article.html'
BUILD_COMPONENTS = BASE_DIR / 'core' / 'scripts' / 'build_components.py'


def generate_post(
    slug: str,
    title: str,
    date: str,
    body_md: str,
    preview: str,
    issue: str | None = None,
    category: str = 'Essay',
    post_type: str = 'Essay',
):
    """마크다운 본문으로 정적 HTML 생성 + index.json 업데이트"""

    # 1. issue 자동 생성 (미제공 시)
    if issue is None:
        posts = _load_index()
        n = len(posts) + 1
        issue = f'Issue {n:03d}'

    # 2. 마크다운 → HTML
    body_html = markdown.markdown(
        body_md,
        extensions=['extra', 'smarty', 'sane_lists']
    )

    # 3. 템플릿 로드 + 플레이스홀더 치환
    template = TEMPLATE_PATH.read_text(encoding='utf-8')
    replacements = {
        '{{title}}': _escape_html(title),
        '{{issue}}': _escape_html(issue),
        '{{date}}': date,
        '{{preview}}': _escape_html(preview),
        '{{content}}': body_html,
        '{{category}}': _escape_html(category),
        '{{slug}}': slug,
        '{{prev_link}}': '',  # floating nav JS가 동적으로 처리
    }
    html = template
    for key, val in replacements.items():
        html = html.replace(key, val)

    # 4. HTML 파일 생성
    post_dir = ARCHIVE_DIR / slug
    post_dir.mkdir(parents=True, exist_ok=True)
    out_path = post_dir / 'index.html'
    out_path.write_text(html, encoding='utf-8')

    # 5. 마크다운 소스 저장 (편집용)
    (post_dir / 'source.md').write_text(body_md, encoding='utf-8')

    # 6. nav/footer 컴포넌트 주입
    _inject_components(out_path)

    # 7. index.json 업데이트
    _update_index(slug, title, date, preview, issue, category, post_type)


def delete_post(slug: str):
    """포스트 삭제 + index.json에서 제거"""
    post_dir = ARCHIVE_DIR / slug
    if post_dir.exists():
        shutil.rmtree(post_dir)
    _remove_from_index(slug)


def _inject_components(filepath: Path) -> None:
    """build_components.py --file 로 nav/footer 마커 주입"""
    if not BUILD_COMPONENTS.exists():
        return
    subprocess.run(
        [sys.executable, str(BUILD_COMPONENTS), '--file', str(filepath)],
        check=False,
        capture_output=True,
    )


def _update_index(
    slug: str,
    title: str,
    date: str,
    preview: str,
    issue: str,
    category: str,
    post_type: str,
) -> None:
    """index.json에 포스트 추가/업데이트 (날짜 역순 정렬)"""
    posts = _load_index()

    existing = next((p for p in posts if p['slug'] == slug), None)
    if existing:
        existing.update({
            'title': title,
            'date': date,
            'preview': preview,
            'issue': issue,
            'category': category,
            'type': post_type,
            'status': existing.get('status', 'published') or 'published',
        })
    else:
        posts.append({
            'slug': slug,
            'title': title,
            'date': date,
            'preview': preview,
            'issue': issue,
            'category': category,
            'type': post_type,
            'status': 'published',
        })

    posts.sort(key=lambda p: p['date'], reverse=True)
    INDEX_PATH.write_text(
        json.dumps(posts, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )


def _remove_from_index(slug: str) -> None:
    """index.json에서 포스트 제거"""
    posts = _load_index()
    posts = [p for p in posts if p['slug'] != slug]
    INDEX_PATH.write_text(
        json.dumps(posts, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )


def _load_index() -> list:
    if not INDEX_PATH.exists():
        return []
    try:
        return json.loads(INDEX_PATH.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, IOError):
        return []


def _escape_html(text: str) -> str:
    return (
        text.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
    )
