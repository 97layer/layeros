#!/usr/bin/env python3
"""
build_archive.py — WOOHWAHAE 아카이브 SSG 빌드

사용:
  python scripts/build_archive.py           # 전체 빌드
  python scripts/build_archive.py --slug essay-010-work-and-essence  # 단일 글

입력:  website/_content/*.md
출력:  website/archive/{slug}/index.html
       website/archive/index.json  (자동 갱신)
"""

import argparse
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

import markdown as md_lib

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
WEBSITE_DIR = ROOT / 'website'
CONTENT_DIR = ROOT / 'website' / '_content'
TEMPLATE_FILE = ROOT / 'website' / '_templates' / 'article.html'
ARCHIVE_DIR = ROOT / 'website' / 'archive'
INDEX_JSON = ARCHIVE_DIR / 'index.json'
SITEMAP_FILE = WEBSITE_DIR / 'sitemap.xml'
SITEMAP_BASE_URL = 'https://woohwahae.kr'
SITEMAP_EXCLUDED_TOP_DIRS = {'assets', 'lab', '_components', '_pages', '_templates'}
SITEMAP_EXCLUDED_FILES = {'404.html'}


# ── frontmatter 파서 ──────────────────────────────────────────────────────────

def parse_frontmatter(text):
    """--- ... --- 블록 파싱 → (meta dict, body str)"""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', text, re.DOTALL)
    if not match:
        return {}, text

    meta = {}
    for line in match.group(1).splitlines():
        if ':' in line:
            key, _, val = line.partition(':')
            meta[key.strip()] = val.strip()

    body = match.group(2).strip()
    return meta, body


# ── 본문 변환 ─────────────────────────────────────────────────────────────────

def convert_body(body_md):
    """마크다운 → HTML (fade-in 클래스 자동 부여)"""
    html = md_lib.markdown(
        body_md,
        extensions=['extra'],   # tables, fenced_code, footnotes 등
    )

    # p 태그에 fade-in 추가
    html = re.sub(r'<p>', '<p class="fade-in">', html)
    # blockquote에 fade-in 추가
    html = re.sub(r'<blockquote>', '<blockquote class="fade-in">', html)

    return html


# ── 이전 글 링크 ──────────────────────────────────────────────────────────────

def make_prev_link(all_meta, current_slug):
    """현재 글보다 한 단계 이전 글 링크 생성"""
    slugs = [m['slug'] for m in all_meta]
    try:
        idx = slugs.index(current_slug)
    except ValueError:
        return ''

    # all_meta는 최신순 정렬 → idx+1이 이전 글
    if idx + 1 < len(all_meta):
        prev = all_meta[idx + 1]
        return (
            f'<a href="../{prev["slug"]}/" class="article-nav-prev">'
            f'← {prev["issue"]} · {prev["title"]}</a>'
        )
    return ''


# ── 단일 글 빌드 ──────────────────────────────────────────────────────────────

def build_one(md_path, template, all_meta):
    text = md_path.read_text(encoding='utf-8')
    meta, body = parse_frontmatter(text)

    slug = meta.get('slug') or md_path.stem
    title = meta.get('title', '')
    issue = meta.get('issue', '')
    date = meta.get('date', '')
    category = meta.get('category', 'Essay')
    preview = meta.get('preview', '')
    read_min = meta.get('readMin', '2')
    dot_label = meta.get('dot_label', '10 yrs · 120 mo')

    content_html = convert_body(body)
    prev_link = make_prev_link(all_meta, slug)

    html = template
    replacements = {
        '{{slug}}': slug,
        '{{title}}': title,
        '{{issue}}': issue,
        '{{date}}': date,
        '{{category}}': category,
        '{{preview}}': preview,
        '{{readMin}}': str(read_min),
        '{{dot_label}}': dot_label,
        '{{prev_link}}': prev_link,
        '{{content}}': content_html,
    }
    for key, val in replacements.items():
        html = html.replace(key, val)

    out_dir = ARCHIVE_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / 'index.html'
    out_file.write_text(html, encoding='utf-8')

    print('[build] %s → %s' % (md_path.name, out_file.relative_to(ROOT)))
    return {
        'slug': slug,
        'title': title,
        'date': date,
        'issue': issue,
        'preview': preview,
        'category': category,
        'readMin': int(read_min) if str(read_min).isdigit() else 2,
    }


# ── index.json 갱신 ──────────────────────────────────────────────────────────

def update_index(built_entries):
    """빌드된 항목으로 index.json 갱신 (날짜 역순 정렬)"""
    # 기존 JSON 읽기 (Lab 카드 등 비-md 항목 보존)
    existing = []
    if INDEX_JSON.exists():
        existing = json.loads(INDEX_JSON.read_text(encoding='utf-8'))

    # slug 기준으로 빌드 결과로 덮어쓰기
    built_slugs = {e['slug'] for e in built_entries}
    preserved = [e for e in existing if e.get('slug') not in built_slugs]
    merged = built_entries + preserved

    # 날짜 역순 정렬 (YYYY.MM.DD 형식 처리)
    def sort_key(e):
        d = e.get('date', '0000.00.00').replace('.', '-')
        try:
            return datetime.strptime(d, '%Y-%m-%d')
        except ValueError:
            return datetime.min

    merged.sort(key=sort_key, reverse=True)

    INDEX_JSON.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    print('[index] %s 갱신 (%d entries)' % (INDEX_JSON.relative_to(ROOT), len(merged)))


def _canonical_url_path(rel_path):
    """website 기준 상대 경로를 canonical URL path로 변환."""
    parts = rel_path.parts
    if not parts:
        return None

    if any(part.startswith('_') for part in parts):
        return None

    top = parts[0]
    if top.startswith('_') or top in SITEMAP_EXCLUDED_TOP_DIRS:
        return None
    if rel_path.name in SITEMAP_EXCLUDED_FILES:
        return None
    if rel_path.name.startswith('_gen'):
        return None

    if rel_path.name == 'index.html':
        if len(parts) == 1:
            return '/'
        return '/' + '/'.join(parts[:-1]) + '/'

    # 동일 stem의 디렉토리 index가 있으면 clean URL(/foo/)을 canonical로 사용.
    if len(parts) == 1:
        dir_index = WEBSITE_DIR / rel_path.stem / 'index.html'
        if dir_index.exists():
            return '/' + rel_path.stem + '/'

    return '/' + rel_path.as_posix()


def _sitemap_meta(url_path):
    """URL path별 changefreq/priority 정책."""
    if url_path == '/':
        return 'weekly', '1.0'
    if url_path in {'/about/', '/archive/', '/practice/'}:
        return 'weekly', '0.9'
    if url_path.startswith('/archive/essay-'):
        return 'monthly', '0.8'
    if url_path.startswith('/archive/'):
        return 'monthly', '0.7'
    if url_path.startswith('/product/'):
        return 'monthly', '0.7'
    if url_path.endswith('.html'):
        return 'monthly', '0.5'
    return 'monthly', '0.6'


def build_sitemap():
    """website/ 실재 HTML 파일을 기준으로 sitemap.xml 자동 생성."""
    url_map = {}

    for html_path in sorted(WEBSITE_DIR.rglob('*.html')):
        rel = html_path.relative_to(WEBSITE_DIR)
        url_path = _canonical_url_path(rel)
        if not url_path:
            continue

        prev = url_map.get(url_path)
        if prev is None:
            url_map[url_path] = html_path
            continue

        # 중복 canonical URL이면 index.html 소스를 우선 채택.
        prev_is_index = prev.name == 'index.html'
        curr_is_index = html_path.name == 'index.html'
        if curr_is_index and not prev_is_index:
            url_map[url_path] = html_path

    urls = sorted(url_map.keys(), key=lambda p: (0 if p == '/' else 1, p))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    for url_path in urls:
        source = url_map[url_path]
        lastmod = datetime.fromtimestamp(source.stat().st_mtime).strftime('%Y-%m-%d')
        changefreq, priority = _sitemap_meta(url_path)
        lines.extend([
            '  <url>',
            f'    <loc>{SITEMAP_BASE_URL}{url_path}</loc>',
            f'    <lastmod>{lastmod}</lastmod>',
            f'    <changefreq>{changefreq}</changefreq>',
            f'    <priority>{priority}</priority>',
            '  </url>',
        ])

    lines.append('</urlset>')
    SITEMAP_FILE.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('[sitemap] %s 갱신 (%d URLs)' % (SITEMAP_FILE.relative_to(ROOT), len(urls)))


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--slug', help='특정 글만 빌드 (slug 지정)')
    args = parser.parse_args()

    if not CONTENT_DIR.exists():
        logger.warning("_content/ 디렉토리 없음: %s (아티클 빌드 스킵)", CONTENT_DIR)
        build_sitemap()
        print('[done] 빌드 완료 (0개)')
        return

    template = TEMPLATE_FILE.read_text(encoding='utf-8')

    # 전체 .md 목록 (빌드 순서용 메타 미리 수집)
    md_files = sorted(CONTENT_DIR.glob('*.md'))
    if not md_files:
        logger.warning("_content/에 .md 파일 없음 (아티클 빌드 스킵)")
        build_sitemap()
        print('[done] 빌드 완료 (0개)')
        return

    # 메타 미리 파싱 (prev_link 계산용)
    all_meta = []
    for f in md_files:
        text = f.read_text(encoding='utf-8')
        meta, _ = parse_frontmatter(text)
        slug = meta.get('slug') or f.stem
        all_meta.append({
            'slug': slug,
            'title': meta.get('title', ''),
            'issue': meta.get('issue', ''),
        })

    # 날짜 기준 역순 정렬 (최신이 앞)
    # _content 파일명이 issue-NNN 순이면 역순 정렬
    all_meta.reverse()

    # 빌드 대상 결정
    if args.slug:
        targets = [f for f in md_files if (f.stem == args.slug or
                   parse_frontmatter(f.read_text('utf-8'))[0].get('slug') == args.slug)]
        if not targets:
            logger.error('slug "%s" 에 해당하는 .md 파일 없음', args.slug)
            return
    else:
        targets = md_files

    built = []
    for f in targets:
        entry = build_one(f, template, all_meta)
        built.append(entry)

    update_index(built)
    build_sitemap()
    print('[done] 빌드 완료 (%d개)' % len(built))


if __name__ == '__main__':
    main()
