"""
WOOHWAHAE Admin Panel
Flask-based CMS for managing archive posts and reviewing LAYER OS pipeline output.
"""

import os
import sys
import json
import time
import logging
import secrets
import subprocess
import functools
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort, Response, stream_with_context
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

# Load .env
try:
    from dotenv import load_dotenv
    _BASE_DIR_FOR_ENV = Path(__file__).resolve().parent.parent.parent
    load_dotenv(_BASE_DIR_FOR_ENV / '.env')
except ImportError:
    pass

# ─── Paths ───
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # LAYER OS root
sys.path.insert(0, str(BASE_DIR))  # core.system 접근용

# Ritual / Growth 모듈
try:
    from core.system.ritual import get_ritual_module
    from core.system.growth import get_growth_module
    _MODULES_AVAILABLE = True
except ImportError:
    _MODULES_AVAILABLE = False
SITE_BASE_URL = os.getenv('SITE_BASE_URL', 'https://woohwahae.kr')
WEBSITE_DIR = BASE_DIR / 'website'
ARCHIVE_DIR = WEBSITE_DIR / 'archive'
PUBLISHED_DIR = BASE_DIR / 'knowledge' / 'assets' / 'published'
UPLOAD_DIR = WEBSITE_DIR / 'assets' / 'img' / 'uploads'
SIGNALS_DIR = BASE_DIR / 'knowledge' / 'signals'
MEMORY_FILE = BASE_DIR / 'knowledge' / 'long_term_memory.json'
AUDIT_LOG_FILE = BASE_DIR / 'knowledge' / 'reports' / 'audit.log'
SERVICE_FILE = BASE_DIR / 'knowledge' / 'service' / 'items.json'
BOOKING_FILE = BASE_DIR / 'knowledge' / 'service' / 'booking.json'
TELEGRAM_LOG_FILE = BASE_DIR / 'logs' / 'telegram.log'
ADMIN_PASSWORD_OVERRIDE_FILE = BASE_DIR / 'knowledge' / 'system' / 'admin_password_hash.json'
SYSTEMD_SERVICES = ['97layer-telegram', '97layer-ecosystem', '97layer-gardener', 'woohwahae-backend', 'cortex-admin']

# ─── App ───
app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / 'templates'),
    static_folder=str(Path(__file__).parent / 'static'),
    static_url_path='/admin-static'
)

# B1: Secret key — env var 필수, fallback 없음
_secret_key = os.getenv('ADMIN_SECRET_KEY')
if not _secret_key:
    raise RuntimeError("ADMIN_SECRET_KEY 환경변수 필수. .env에 설정하세요.")
app.secret_key = _secret_key

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['DEBUG'] = False
app.config['PROPAGATE_EXCEPTIONS'] = False
app.config['APPLICATION_ROOT'] = '/admin'
app.config['PREFERRED_URL_SCHEME'] = 'https'

# WSGI 미들웨어: nginx X-Forwarded-Prefix → SCRIPT_NAME (url_for prefix 적용)
# before_request보다 앞서 실행되어 URL adapter 생성 전에 SCRIPT_NAME 설정
_original_wsgi = app.wsgi_app

def _prefix_middleware(environ, start_response):
    prefix = environ.get('HTTP_X_FORWARDED_PREFIX', '')
    if prefix:
        environ['SCRIPT_NAME'] = prefix
    return _original_wsgi(environ, start_response)

app.wsgi_app = _prefix_middleware

# B2: 쿠키 보안
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='Strict',
    PERMANENT_SESSION_LIFETIME=3600,  # 1시간 세션 만료
)

_admin_hash = os.getenv('ADMIN_PASSWORD_HASH')
if not _admin_hash:
    raise RuntimeError("ADMIN_PASSWORD_HASH 환경변수 필수. .env에 설정하세요.")


def _load_admin_password_hash(default_hash: str) -> str:
    if not ADMIN_PASSWORD_OVERRIDE_FILE.exists():
        return default_hash
    try:
        payload = json.loads(ADMIN_PASSWORD_OVERRIDE_FILE.read_text(encoding='utf-8'))
        override_hash = str(payload.get('password_hash', '')).strip()
        if override_hash:
            return override_hash
    except (json.JSONDecodeError, OSError):
        pass
    return default_hash


def _save_admin_password_hash(password_hash: str) -> None:
    ADMIN_PASSWORD_OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ADMIN_PASSWORD_OVERRIDE_FILE.write_text(
        json.dumps(
            {
                'password_hash': password_hash,
                'updated_at': datetime.utcnow().isoformat() + 'Z',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )


ADMIN_PASSWORD_HASH = _load_admin_password_hash(_admin_hash)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
ALLOWED_MIME = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml'}

# ─── Logging ───
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# B10: Audit logger
audit_logger = logging.getLogger('audit')
try:
    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _audit_handler = logging.FileHandler(str(AUDIT_LOG_FILE))
    _audit_handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    audit_logger.addHandler(_audit_handler)
    audit_logger.setLevel(logging.INFO)
except Exception:
    pass  # 로그 파일 생성 실패해도 서버 동작에 영향 없음


def _audit(action: str, detail: str = '') -> None:
    """B10: 관리자 액션 감사 로그"""
    ip = request.remote_addr if request else 'system'
    audit_logger.info("ip=%s action=%s detail=%s", ip, action, detail)


# ─── Booking storage helpers ───
_booking_lock = threading.Lock()


def _booking_default() -> dict:
    return {"bookings": [], "cards": [], "visit_logs": []}


def _atomic_write(path: Path, payload: dict) -> None:
    tmp_path = path.with_suffix('.tmp')
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    tmp_path.replace(path)


def _load_bookings() -> dict:
    BOOKING_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not BOOKING_FILE.exists():
        return _booking_default()
    try:
        return json.loads(BOOKING_FILE.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        logger.error("booking.json parse error — resetting to default")
        return _booking_default()


def _save_bookings(data: dict) -> None:
    with _booking_lock:
        _atomic_write(BOOKING_FILE, data)


def _next_booking_id(data: dict) -> str:
    existing = [b.get('id', '') for b in data.get('bookings', [])]
    nums = []
    for bid in existing:
        if isinstance(bid, str) and bid.startswith('b') and bid[1:].isdigit():
            nums.append(int(bid[1:]))
    nxt = max(nums) + 1 if nums else 1
    return f"b{nxt:04d}"


BOOKING_STATUSES = ['pending', 'confirmed', 'done']


def _find_booking(data: dict, booking_id: str):
    for b in data.get('bookings', []):
        if b.get('id') == booking_id:
            return b
    return None


def _upsert_card(data: dict, card: dict):
    # replace existing card for booking_id
    cards = data.setdefault('cards', [])
    updated = False
    for idx, c in enumerate(cards):
        if c.get('booking_id') == card.get('booking_id'):
            cards[idx] = card
            updated = True
            break
    if not updated:
        cards.append(card)


# B8: 로그인 실패 카운터 (인메모리, 재시작 시 초기화)
_login_attempts: dict = defaultdict(list)
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 15 * 60


def _client_ip() -> str:
    forwarded = request.headers.get('X-Forwarded-For', '').strip()
    if forwarded:
        return forwarded.split(',')[0].strip()[:64]
    return (request.remote_addr or 'unknown')[:64]


def _prune_login_attempts(ip: str, now_ts=None) -> list:
    if now_ts is None:
        now_ts = time.time()
    cutoff = now_ts - LOGIN_WINDOW_SECONDS
    attempts = _login_attempts.get(ip, [])
    fresh = [ts for ts in attempts if ts >= cutoff]
    _login_attempts[ip] = fresh
    return fresh


def _is_login_limited(ip: str) -> bool:
    return len(_prune_login_attempts(ip)) >= LOGIN_MAX_ATTEMPTS


def _record_login_failure(ip: str) -> int:
    attempts = _prune_login_attempts(ip)
    attempts.append(time.time())
    _login_attempts[ip] = attempts
    return len(attempts)


# ─── B3: CSRF ───
_CSRF_EXEMPT_PATHS = {'/login'}


def _generate_csrf_token() -> str:
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


app.jinja_env.globals['csrf_token'] = _generate_csrf_token


# ─── B4: 보안 응답 헤더 ───
@app.after_request
def set_security_headers(response):
    """CSP, X-Frame-Options, HSTS 등 보안 헤더 일괄 적용"""
    # XSS 방어: 인라인 스크립트·외부 리소스 제한
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    # 클릭재킹 방어
    response.headers['X-Frame-Options'] = 'DENY'
    # MIME 스니핑 방어
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # 레퍼러 최소화
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # XSS 필터 (레거시 브라우저)
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # 권한 정책 — 불필요한 브라우저 API 차단
    response.headers['Permissions-Policy'] = (
        'camera=(), microphone=(), geolocation=(), payment=()'
    )
    # HSTS — HTTPS 강제 (1년, 서브도메인 포함)
    response.headers['Strict-Transport-Security'] = (
        'max-age=31536000; includeSubDomains'
    )
    # 에러 응답에서 Flask 버전 노출 차단
    response.headers.pop('Server', None)
    return response


@app.before_request
def csrf_protect() -> None:
    """B3: POST 요청 CSRF 검증 (로그인 제외)"""
    if request.method != 'POST':
        return
    if request.path in _CSRF_EXEMPT_PATHS:
        return
    # JSON API: X-CSRF-Token 헤더 허용 (SameSite=Strict 보완)
    if request.is_json:
        token = request.headers.get('X-CSRF-Token')
    else:
        token = request.form.get('_csrf_token')
    expected = session.get('_csrf_token')
    if not expected or token != expected:
        _audit('csrf_violation', request.path)
        abort(403)


# ─── Auth ───
def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login():
    ip = _client_ip()
    if request.method == 'POST':
        # B8: sliding window rate limiting
        if _is_login_limited(ip):
            _audit('login_blocked', 'too_many_attempts')
            return jsonify({'error': '로그인 시도 횟수 초과. 잠시 후 다시 시도하세요.'}), 429

        password = request.form.get('password', '')
        if check_password_hash(ADMIN_PASSWORD_HASH, password):
            _login_attempts.pop(ip, None)
            session['logged_in'] = True
            session.permanent = True
            _audit('login_success')
            return redirect(url_for('dashboard'))

        attempt_count = _record_login_failure(ip)
        _audit('login_failed', 'attempt_%d' % attempt_count)
        flash('비밀번호가 올바르지 않습니다.')
    return render_template('login.html')


@app.route('/logout')
def logout():
    _audit('logout')
    session.clear()
    return redirect(url_for('login'))


def _archive_entry_is_pending(entry: dict) -> bool:
    raw_url = str(entry.get('url', '')).strip()
    slug = str(entry.get('slug', '')).strip().lower()
    if raw_url in {'#', '/#'}:
        return True
    return 'mock-' in slug


def _archive_entry_public_url(entry: dict) -> str:
    raw_url = str(entry.get('url', '')).strip()
    if raw_url and raw_url not in {'#', '/#'}:
        if raw_url.startswith('/') or raw_url.startswith('http://') or raw_url.startswith('https://'):
            return raw_url
        return '/archive/' + raw_url.lstrip('./')
    slug = str(entry.get('slug', '')).strip()
    if slug:
        return f'/archive/{slug}/'
    return '/archive/'


def _archive_entry_sort_key(entry: dict) -> datetime:
    date_text = str(entry.get('date', '')).strip()
    if not date_text:
        return datetime.min
    for fmt in ('%Y.%m.%d', '%Y-%m-%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(date_text, fmt)
        except ValueError:
            continue
    return datetime.min


def _build_archive_board(posts: list[dict]) -> dict:
    pending_count = 0
    rows = []
    for item in posts:
        pending = _archive_entry_is_pending(item)
        if pending:
            pending_count += 1
        slug = str(item.get('slug', '')).strip()
        rows.append({
            'type': item.get('type') or 'Entry',
            'issue': item.get('issue') or 'Issue',
            'title': item.get('title') or 'Untitled',
            'preview': item.get('preview') or '',
            'date': item.get('date') or 'N/A',
            'status': 'pending' if pending else 'live',
            'status_label': 'PENDING' if pending else 'LIVE',
            'action_label': '편집' if pending else '열기',
            'action_url': url_for('archive_edit', slug=slug) if (pending and slug) else _archive_entry_public_url(item),
            'sort_key': _archive_entry_sort_key(item),
        })
    rows.sort(key=lambda row: row['sort_key'], reverse=True)
    for row in rows:
        row.pop('sort_key', None)
    total = len(posts)
    return {
        'total': total,
        'pending': pending_count,
        'published': max(total - pending_count, 0),
        'rows': rows,
    }


# ─── Dashboard ───
@app.route('/')
@login_required
def dashboard():
    posts = _load_index()
    pipeline_count = _count_pipeline_items()
    today = datetime.now().strftime('%Y-%m-%d')
    period = datetime.now().strftime('%Y-%m')

    due_clients = []
    growth_snapshot = {}
    if _MODULES_AVAILABLE:
        try:
            due_clients = get_ritual_module().get_due_clients()
        except Exception as e:
            logger.error("dashboard due_clients error: %s", e)
        try:
            gm = get_growth_module()
            month_data = gm.get_month(period)
            growth_snapshot = {
                'period': period,
                'total': month_data.get('atelier', 0) + month_data.get('consulting', 0) + month_data.get('products', 0),
                'atelier': month_data.get('atelier', 0),
                'consulting': month_data.get('consulting', 0),
                'products': month_data.get('products', 0),
            }
        except Exception as e:
            logger.error("dashboard growth_snapshot error: %s", e)

    signal_count = len(list(SIGNALS_DIR.glob('*.json'))) if SIGNALS_DIR.exists() else 0
    archive_board = _build_archive_board(posts)

    return render_template('dashboard.html',
                           post_count=len(posts),
                           pipeline_count=pipeline_count,
                           signal_count=signal_count,
                           due_clients=due_clients,
                           growth_snapshot=growth_snapshot,
                           archive_board=archive_board,
                           today=today,
                           period=period)


# ─── Archive CRUD ───
@app.route('/archive')
@login_required
def archive_list():
    posts = _load_index()
    return render_template('archive_list.html', posts=posts)


@app.route('/archive/new', methods=['GET', 'POST'])
@login_required
def archive_new():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        slug = request.form.get('slug', '').strip()
        body = request.form.get('body', '').strip()
        preview = request.form.get('preview', '').strip()

        if not title or not slug or not body:
            flash('제목, 슬러그, 본문은 필수입니다.')
            return render_template('archive_edit.html', mode='new',
                                   post={'title': title, 'slug': slug,
                                         'body': body, 'preview': preview})

        # Sanitize slug
        slug = _sanitize_slug(slug)

        # Generate static HTML
        from core.admin.utils.post_generator import generate_post
        date_str = datetime.now().strftime('%Y.%m.%d')
        generate_post(slug, title, date_str, body, preview)

        _audit('archive_create', slug)
        flash(f'"{title}" 포스트가 생성되었습니다.')
        return redirect(url_for('archive_list'))

    return render_template('archive_edit.html', mode='new', post={})


@app.route('/archive/<slug>/edit', methods=['GET', 'POST'])
@login_required
def archive_edit(slug):
    posts = _load_index()
    post = next((p for p in posts if p['slug'] == slug), None)

    if not post:
        flash('포스트를 찾을 수 없습니다.')
        return redirect(url_for('archive_list'))

    # Load markdown source
    md_path = ARCHIVE_DIR / slug / 'source.md'
    body = md_path.read_text(encoding='utf-8') if md_path.exists() else ''

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        body = request.form.get('body', '').strip()
        preview = request.form.get('preview', '').strip()

        if not title or not body:
            flash('제목과 본문은 필수입니다.')
            return render_template('archive_edit.html', mode='edit',
                                   post={**post, 'body': body, 'preview': preview})

        from core.admin.utils.post_generator import generate_post
        generate_post(slug, title, post['date'], body, preview)

        _audit('archive_edit', slug)
        flash(f'"{title}" 포스트가 수정되었습니다.')
        return redirect(url_for('archive_list'))

    post['body'] = body
    return render_template('archive_edit.html', mode='edit', post=post)


@app.route('/archive/<slug>/delete', methods=['POST'])
@login_required
def archive_delete(slug):
    from core.admin.utils.post_generator import delete_post
    delete_post(slug)
    _audit('archive_delete', slug)
    flash('포스트가 삭제되었습니다.')
    return redirect(url_for('archive_list'))


# ─── Publish (git push) ───
@app.route('/publish', methods=['POST'])
@login_required
def publish():
    from core.admin.utils.git_publisher import publish_to_website
    success, message = publish_to_website()
    _audit('publish', 'success=%s' % success)
    flash(message)
    return redirect(url_for('dashboard'))


# ─── Pipeline Review ───
@app.route('/pipeline')
@login_required
def pipeline():
    items = _load_pipeline_items()
    return render_template('pipeline.html', items=items)


@app.route('/pipeline/<path:item_id>/adopt', methods=['POST'])
@login_required
def pipeline_adopt(item_id):
    """파이프라인 콘텐츠를 아카이브 포스트로 채택"""
    # B9: Path traversal 방어
    item_path = (PUBLISHED_DIR / item_id).resolve()
    if not str(item_path).startswith(str(PUBLISHED_DIR.resolve())):
        _audit('path_traversal_blocked', item_id)
        abort(400)

    meta_path = item_path / 'meta.json'
    essay_path = item_path / 'archive_essay.txt'

    if not essay_path.exists():
        flash('에세이 파일을 찾을 수 없습니다.')
        return redirect(url_for('pipeline'))

    body = essay_path.read_text(encoding='utf-8')
    title = ''
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            title = meta.get('title', meta.get('signal_id', item_id))
        except (json.JSONDecodeError, IOError):
            pass

    if not title:
        title = item_id.replace('/', ' — ')

    slug = _sanitize_slug(title)
    date_str = datetime.now().strftime('%Y.%m.%d')
    preview = body[:100] + '...' if len(body) > 100 else body

    from core.admin.utils.post_generator import generate_post
    generate_post(slug, title, date_str, body, preview)

    _audit('pipeline_adopt', slug)
    flash(f'"{title}" 파이프라인 콘텐츠가 채택되었습니다.')
    return redirect(url_for('archive_list'))


# ─── Cockpit (Second Brain UI) ───
@app.route('/cockpit')
@login_required
def cockpit():
    """세컨드 브레인 주입 및 소통 창구"""
    memory = {}
    if MEMORY_FILE.exists():
        try:
            memory = json.loads(MEMORY_FILE.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, IOError):
            pass

    # 랭킹 데이터 추출
    concepts = sorted(memory.get('concepts', {}).items(), key=lambda x: x[1], reverse=True)[:10]
    experiences = memory.get('experiences', [])[-5:]

    return render_template('cockpit.html', concepts=concepts, experiences=experiences)


@app.route('/api/insight', methods=['POST'])
@login_required
def api_insight():
    """인사이트 주입 API"""
    data = request.json or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': '내용이 없습니다.'}), 400

    from core.system.cortex_edge import get_cortex
    cortex = get_cortex()
    result = cortex.inject_signal(text, source="web_admin")

    return jsonify(result)


@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    """AIEngine 대화 API (Deep RAG)"""
    data = request.json or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': '내용이 없습니다.'}), 400

    try:
        from core.system.cortex_edge import get_cortex
        cortex = get_cortex()
        result = cortex.query("admin", text)
        return jsonify({'response': result['response']})
    except Exception as e:
        logger.error("api_chat error: %s", e)
        return jsonify({'error': '내부 오류'}), 500


# ─── Image Upload ───
@app.route('/upload', methods=['POST'])
@login_required
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다.'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': '파일명이 없습니다.'}), 400

    if not _allowed_file(file.filename):
        return jsonify({'error': '허용되지 않는 파일 형식입니다.'}), 400

    # B9: MIME type 검증 (python-magic 없을 때 graceful fallback)
    try:
        import magic
        file_bytes = file.read(2048)
        file.seek(0)
        mime = magic.from_buffer(file_bytes, mime=True)
        if mime not in ALLOWED_MIME:
            return jsonify({'error': '허용되지 않는 파일 형식입니다.'}), 400
    except ImportError:
        pass  # python-magic 미설치 시 확장자 검증만 사용

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{filename}"
    file.save(str(UPLOAD_DIR / filename))

    _audit('upload', filename)
    return jsonify({
        'url': f'/assets/img/uploads/{filename}',
        'filename': filename
    })


# ─── Growth Dashboard ───

@app.route('/growth')
@login_required
def growth_dashboard():
    if not _MODULES_AVAILABLE:
        flash('모듈 로드 실패. core/system 경로 확인.')
        return redirect(url_for('dashboard'))

    gm = get_growth_module()
    rm = get_ritual_module()
    period = request.args.get('period', datetime.now().strftime('%Y-%m'))

    try:
        gm.auto_count_content(period)
        gm.auto_count_service(period)
    except Exception as e:
        logger.error("growth auto_count error: %s", e)

    try:
        data = gm.get_month(period)
        trend = gm.get_trend(months=6)
        periods = gm.list_periods()
        stats = rm.get_stats()
    except Exception as e:
        logger.error("growth data fetch error: %s", e)
        data, trend, periods, stats = {}, [], [], {}

    _audit('growth_view', 'period=%s' % period)
    return render_template('growth.html',
        data=data,
        trend=trend,
        periods=periods,
        stats=stats,
        current_period=period,
    )


@app.route('/growth/revenue', methods=['POST'])
@login_required
def growth_revenue():
    if not _MODULES_AVAILABLE:
        return jsonify({'error': '모듈 없음'}), 503

    period = request.form.get('period', datetime.now().strftime('%Y-%m'))
    gm = get_growth_module()

    try:
        gm.record_revenue(
            period,
            atelier=int(request.form.get('atelier', 0) or 0),
            consulting=int(request.form.get('consulting', 0) or 0),
            products=int(request.form.get('products', 0) or 0),
        )
    except Exception as e:
        logger.error("growth record_revenue error: %s", e)
        flash('수익 저장 실패')
        return redirect(url_for('growth_dashboard', period=period))

    _audit('revenue_recorded', 'period=%s' % period)
    return redirect(url_for('growth_dashboard', period=period))


# ─── Ritual (고객 관리) ───

@app.route('/ritual')
@login_required
def ritual_dashboard():
    if not _MODULES_AVAILABLE:
        flash('모듈 로드 실패. core/system 경로 확인.')
        return redirect(url_for('dashboard'))

    rm = get_ritual_module()
    try:
        clients = rm.list_clients()
        due_clients = rm.get_due_clients()
        stats = rm.get_stats()
    except Exception as e:
        logger.error("ritual data fetch error: %s", e)
        clients, due_clients, stats = [], [], {}

    today = datetime.now().strftime('%Y-%m-%d')
    _audit('ritual_view')
    return render_template('ritual.html',
        clients=clients,
        due_clients=due_clients,
        stats=stats,
        today=today,
    )


@app.route('/ritual/add', methods=['POST'])
@login_required
def ritual_add():
    if not _MODULES_AVAILABLE:
        flash('모듈 없음')
        return redirect(url_for('ritual_dashboard'))

    name = request.form.get('name', '').strip()
    if not name:
        flash('이름은 필수입니다.')
        return redirect(url_for('ritual_dashboard'))

    rm = get_ritual_module()
    try:
        client = rm.create_client(
            name=name,
            hair_type=request.form.get('hair_type', '').strip(),
            rhythm=request.form.get('rhythm', '보통'),
            phone=request.form.get('phone', '').strip(),
        )
        _audit('ritual_add', 'client=%s' % client['client_id'])
        flash('"%s" 고객이 등록되었습니다.' % name)
    except Exception as e:
        logger.error("ritual create_client error: %s", e)
        flash('고객 등록 실패')

    return redirect(url_for('ritual_dashboard'))


@app.route('/ritual/visit', methods=['POST'])
@login_required
def ritual_visit():
    if not _MODULES_AVAILABLE:
        flash('모듈 없음')
        return redirect(url_for('ritual_dashboard'))

    client_id = request.form.get('client_id', '').strip()
    service = request.form.get('service', '').strip()

    if not client_id or not service:
        flash('고객과 서비스는 필수입니다.')
        return redirect(url_for('ritual_dashboard'))

    rm = get_ritual_module()
    try:
        amount_raw = request.form.get('amount', '0') or '0'
        weeks_raw = request.form.get('next_visit_weeks', '0') or '0'
        sat_raw = request.form.get('satisfaction', '').strip()
        visit_date = request.form.get('visit_date', '').strip() or None

        rm.add_visit(
            client_id=client_id,
            service=service,
            public_note=request.form.get('public_note', '').strip(),
            notes=request.form.get('notes', '').strip(),
            amount=int(amount_raw) if amount_raw.isdigit() else 0,
            next_visit_weeks=int(weeks_raw) if weeks_raw.isdigit() else 0,
            satisfaction=int(sat_raw) if sat_raw.isdigit() else None,
            visit_date=visit_date,
        )
        _audit('ritual_visit', 'client=%s service=%s' % (client_id, service))
        flash('방문 기록이 저장되었습니다.')
    except Exception as e:
        logger.error("ritual add_visit error: %s", e)
        flash('방문 기록 저장 실패')

    return redirect(url_for('ritual_dashboard'))


@app.route('/ritual/update', methods=['POST'])
@login_required
def ritual_update():
    if not _MODULES_AVAILABLE:
        flash('모듈 없음')
        return redirect(url_for('ritual_dashboard'))

    client_id = request.form.get('client_id', '').strip()
    if not client_id:
        flash('고객 ID 필요')
        return redirect(url_for('ritual_dashboard'))

    rm = get_ritual_module()
    try:
        updates = {
            'hair_type': request.form.get('hair_type', '').strip(),
            'phone': request.form.get('phone', '').strip(),
            'preference_notes': request.form.get('preference_notes', '').strip(),
        }
        if request.form.get('name', '').strip():
            updates['name'] = request.form.get('name').strip()
        if request.form.get('rhythm', '').strip():
            updates['rhythm'] = request.form.get('rhythm').strip()

        rm.update_client(client_id, **updates)
        _audit('ritual_update', 'client=%s' % client_id)
        flash('고객 정보가 수정되었습니다.')
    except Exception as e:
        logger.error("ritual update_client error: %s", e)
        flash('고객 정보 수정 실패')

    return redirect(url_for('ritual_dashboard'))


@app.route('/ritual/portal-link/<client_id>')
@login_required
def ritual_portal_link(client_id):
    if not _MODULES_AVAILABLE:
        return jsonify({'error': '모듈 없음'}), 503

    # B9: client_id 형식 검증
    import re
    if not re.match(r'^client_\d{4}$', client_id):
        return jsonify({'error': '잘못된 client_id'}), 400

    rm = get_ritual_module()
    client = rm.get_client(client_id)
    if not client:
        return jsonify({'error': '고객 없음'}), 404

    token = client.get('portal_token', '')
    _audit('ritual_portal_link', 'client=%s' % client_id)
    return jsonify({
        'portal_url': '%s/me/%s' % (SITE_BASE_URL, token),
        'consult_url': '%s/consult/%s' % (SITE_BASE_URL, token),
        'token': token,
    })


# ─── Booking (예약/카드/로그) ───


@app.route('/bookings')
@login_required
def bookings_dashboard():
    data = _load_bookings()
    bookings = sorted(data.get('bookings', []), key=lambda b: b.get('created_at', ''), reverse=True)
    _audit('bookings_view')
    return render_template(
        'bookings.html',
        bookings=bookings,
        stats={
            'pending': sum(1 for b in bookings if b.get('status') == 'pending'),
            'confirmed': sum(1 for b in bookings if b.get('status') == 'confirmed'),
            'done': sum(1 for b in bookings if b.get('status') == 'done'),
        },
    )


@app.route('/bookings/add', methods=['POST'])
@login_required
def bookings_add():
    payload = request.form
    name = payload.get('name', '').strip()
    if not name:
        flash('이름은 필수입니다.')
        return redirect(url_for('bookings_dashboard'))

    data = _load_bookings()
    booking_id = _next_booking_id(data)
    now = datetime.utcnow().isoformat() + 'Z'
    booking = {
        'id': booking_id,
        'name': name,
        'phone': payload.get('phone', '').strip(),
        'email': payload.get('email', '').strip(),
        'preferred_date': payload.get('preferred_date', '').strip(),
        'preferred_time': payload.get('preferred_time', '').strip(),
        'service': payload.get('service', '').strip(),
        'note': payload.get('note', '').strip(),
        'client_id': payload.get('client_id', '').strip(),
        'status': 'pending',
        'created_at': now,
        'updated_at': now,
    }

    card = {
        'booking_id': booking_id,
        'wash_freq': payload.get('wash_freq', '').strip(),
        'dry_method': payload.get('dry_method', '').strip(),
        'product': payload.get('product', '').strip(),
        'note': payload.get('card_note', '').strip(),
        'updated_at': now,
    }
    if any(card.values()):
        booking['card'] = card
        _upsert_card(data, card)

    data.setdefault('bookings', []).append(booking)
    _save_bookings(data)
    _audit('booking_add', f"id={booking_id} name={name}")
    flash('예약이 추가되었습니다.')
    return redirect(url_for('bookings_dashboard'))


@app.route('/bookings/<booking_id>/update', methods=['POST'])
@login_required
def bookings_update(booking_id):
    data = _load_bookings()
    booking = _find_booking(data, booking_id)
    if not booking:
        flash('예약을 찾을 수 없습니다.')
        return redirect(url_for('bookings_dashboard'))

    payload = request.form
    status = payload.get('status', booking.get('status', 'pending')).strip()
    if status in BOOKING_STATUSES:
        booking['status'] = status
    booking['preferred_date'] = payload.get('preferred_date', booking.get('preferred_date', '')).strip()
    booking['preferred_time'] = payload.get('preferred_time', booking.get('preferred_time', '')).strip()
    booking['service'] = payload.get('service', booking.get('service', '')).strip()
    booking['note'] = payload.get('note', booking.get('note', '')).strip()
    booking['client_id'] = payload.get('client_id', booking.get('client_id', '')).strip()

    now = datetime.utcnow().isoformat() + 'Z'
    card = {
        'booking_id': booking_id,
        'wash_freq': payload.get('wash_freq', '').strip(),
        'dry_method': payload.get('dry_method', '').strip(),
        'product': payload.get('product', '').strip(),
        'note': payload.get('card_note', '').strip(),
        'updated_at': now,
    }
    if any(card.values()):
        booking['card'] = card
        _upsert_card(data, card)

    # 방문 기록 생성 (옵션)
    if booking.get('client_id') and payload.get('make_visit') == '1' and _MODULES_AVAILABLE:
        try:
            rm = get_ritual_module()
            rm.add_visit(
                client_id=booking['client_id'],
                service=booking.get('service', '') or '방문',
                public_note=payload.get('public_note', '').strip(),
                notes=booking.get('note', ''),
                next_visit_weeks=int(payload.get('next_visit_weeks', '0') or 0),
            )
            visit_log = {
                'id': f"v{len(data.get('visit_logs', [])) + 1:04d}",
                'booking_id': booking_id,
                'client_id': booking['client_id'],
                'service': booking.get('service', ''),
                'created_at': now,
            }
            data.setdefault('visit_logs', []).append(visit_log)
            booking['status'] = 'done'
            flash('방문 기록이 생성되었습니다.')
        except Exception as e:
            logger.error("booking visit add error: %s", e)
            flash('방문 기록 생성에 실패했습니다.')

    booking['updated_at'] = now
    _save_bookings(data)
    _audit('booking_update', f"id={booking_id} status={booking.get('status')}")
    flash('예약이 업데이트되었습니다.')
    return redirect(url_for('bookings_dashboard'))


@app.route('/bookings/<booking_id>/delete', methods=['POST'])
@login_required
def bookings_delete(booking_id):
    data = _load_bookings()
    before = len(data.get('bookings', []))
    data['bookings'] = [b for b in data.get('bookings', []) if b.get('id') != booking_id]
    data['cards'] = [c for c in data.get('cards', []) if c.get('booking_id') != booking_id]
    data['visit_logs'] = [v for v in data.get('visit_logs', []) if v.get('booking_id') != booking_id]
    _save_bookings(data)
    _audit('booking_delete', f"id={booking_id} removed={before - len(data['bookings'])}")
    flash('예약이 삭제되었습니다.')
    return redirect(url_for('bookings_dashboard'))


# ─── SSE 실시간 스트림 ───

# 메모리 캐시 (TTL 기반, 스레드 안전)
_cache_lock = threading.Lock()
_sse_cache: dict = {}
_SSE_CACHE_TTL = 60  # seconds


def _cache_get(key: str):
    with _cache_lock:
        entry = _sse_cache.get(key)
        if entry and time.time() - entry['ts'] < _SSE_CACHE_TTL:
            return entry['val'], True
    return None, False


def _cache_set(key: str, val):
    with _cache_lock:
        _sse_cache[key] = {'val': val, 'ts': time.time()}


def _check_service_status(name: str) -> str:
    """systemctl is-active 결과 반환. 60초 캐시."""
    cache_key = 'svc_%s' % name
    cached, hit = _cache_get(cache_key)
    if hit:
        return cached
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', name],
            capture_output=True, text=True, timeout=3
        )
        status = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        status = 'unknown'
    _cache_set(cache_key, status)
    return status


def _current_period() -> str:
    return datetime.now().strftime('%Y-%m')


def _sse_event(data: dict) -> str:
    return 'data: %s\n\n' % json.dumps(data, ensure_ascii=False)


@app.route('/api/stream')
@login_required
def event_stream():
    """SSE: 대시보드 실시간 이벤트 스트림 (30초 폴링)."""
    @stream_with_context
    def generate():
        while True:
            try:
                # L4: 재방문 알림 (캐시)
                if _MODULES_AVAILABLE:
                    try:
                        due, hit = _cache_get('due_clients')
                        if not hit:
                            due = get_ritual_module().get_due_clients()
                            _cache_set('due_clients', due)
                        yield _sse_event({'type': 'clients_due', 'count': len(due), 'clients': due[:5]})
                    except Exception as e:
                        logger.error("sse due_clients: %s", e)

                # L3: 파이프라인 (캐시 적용됨)
                yield _sse_event({'type': 'pipeline', 'count': _count_pipeline_items()})

                # L5: 성장 (캐시)
                if _MODULES_AVAILABLE:
                    try:
                        period = _current_period()
                        month_data, hit = _cache_get('growth_%s' % period)
                        if not hit:
                            month_data = get_growth_module().get_month(period)
                            _cache_set('growth_%s' % period, month_data)
                        total = month_data.get('atelier', 0) + month_data.get('consulting', 0) + month_data.get('products', 0)
                        yield _sse_event({'type': 'growth', 'total': total, 'period': period})
                    except Exception as e:
                        logger.error("sse growth: %s", e)

                # System: 서비스 상태 (캐시 적용됨)
                for svc in SYSTEMD_SERVICES:
                    yield _sse_event({'type': 'service', 'name': svc, 'status': _check_service_status(svc)})

                yield _sse_event({'type': 'heartbeat', 'ts': int(time.time())})

            except GeneratorExit:
                break
            except Exception as e:
                logger.error("sse generate error: %s", e)

            time.sleep(30)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'}
    )


# ─── 명령 API ───

def _cmd_restart_service(params: dict) -> dict:
    name = params.get('name', '')
    if name not in SYSTEMD_SERVICES:
        return {'ok': False, 'error': '허용되지 않은 서비스'}
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'restart', name],
            capture_output=True, text=True, timeout=10
        )
        details = (result.stdout or '') + ("\n" + result.stderr if result.stderr else '')
        return {
            'ok': result.returncode == 0,
            'returncode': result.returncode,
            'output': details.strip(),
        }
    except subprocess.TimeoutExpired:
        return {'ok': False, 'error': 'timeout'}


def _cmd_trigger_gardener(params: dict) -> dict:
    try:
        gardener_path = BASE_DIR / 'core' / 'agents' / 'gardener.py'
        if not gardener_path.exists():
            return {'ok': False, 'error': 'gardener.py 없음'}
        result = subprocess.Popen(
            [sys.executable, str(gardener_path), '--run-now'],
            cwd=str(BASE_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return {'ok': True, 'pid': result.pid}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _cmd_inject_signal(params: dict) -> dict:
    text = params.get('text', '').strip()
    if not text:
        return {'ok': False, 'error': '텍스트 없음'}
    try:
        signal_id = 'manual_%s' % int(time.time())
        signal = {
            'signal_id': signal_id,
            'type': 'text',
            'content': text,
            'source': 'admin_command',
            'created_at': datetime.now().isoformat(),
        }
        SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = SIGNALS_DIR / ('%s.json' % signal_id)
        out_path.write_text(json.dumps(signal, ensure_ascii=False, indent=2), encoding='utf-8')
        return {'ok': True, 'signal_id': signal_id}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


_COMMAND_HANDLERS = {
    'restart_service': _cmd_restart_service,
    'trigger_gardener': _cmd_trigger_gardener,
    'inject_signal': _cmd_inject_signal,
}


@app.route('/api/command', methods=['POST'])
@login_required
def command_api():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'ok': False, 'error': '잘못된 JSON 본문'}), 400

    action = data.get('action', '')
    params = data.get('params', {})
    if not isinstance(params, dict):
        return jsonify({'ok': False, 'error': 'params는 객체(JSON object)여야 합니다.'}), 400

    if action not in _COMMAND_HANDLERS:
        return jsonify({'ok': False, 'error': '알 수 없는 명령: %s' % action}), 400

    try:
        result = _COMMAND_HANDLERS[action](params)
    except Exception as e:
        logger.error("command_api handler error: %s", e, exc_info=True)
        result = {'ok': False, 'error': '명령 실행 중 내부 오류'}

    _audit('command', 'action=%s' % action)
    return jsonify(result)


# ─── 서비스 관리 ───

def _load_service_items() -> list:
    if not SERVICE_FILE.exists():
        return []
    try:
        return json.loads(SERVICE_FILE.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, IOError):
        return []


def _save_service_items(items: list) -> None:
    SERVICE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SERVICE_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')


@app.route('/service')
@login_required
def service_admin():
    items = _load_service_items()
    _audit('service_view')
    return render_template('service.html', items=items)


@app.route('/service/add', methods=['POST'])
@login_required
def service_add():
    name = request.form.get('name', '').strip()
    if not name:
        flash('이름은 필수입니다.')
        return redirect(url_for('service_admin'))

    price_raw = request.form.get('price', '0').strip()
    try:
        price = int(price_raw) if price_raw else 0
    except ValueError:
        flash('가격은 숫자만 입력하세요.')
        return redirect(url_for('service_admin'))

    items = _load_service_items()
    item_id = 'item_%03d' % (len(items) + 1)
    items.append({
        'item_id': item_id,
        'name': name,
        'category': request.form.get('category', 'service'),
        'price': price,
        'active': True,
        'description': request.form.get('description', '').strip(),
        'url': request.form.get('url', '').strip(),
        'created_at': datetime.now().strftime('%Y-%m-%d'),
    })
    _save_service_items(items)
    _audit('service_add', 'name=%s' % name)
    flash('"%s" 추가되었습니다.' % name)
    return redirect(url_for('service_admin'))


@app.route('/service/<item_id>/toggle', methods=['POST'])
@login_required
def service_toggle(item_id):
    items = _load_service_items()
    for item in items:
        if item.get('item_id') == item_id:
            item['active'] = not item.get('active', True)
            break
    _save_service_items(items)
    _audit('service_toggle', 'item=%s' % item_id)
    return redirect(url_for('service_admin'))


# ─── 도구 ───

@app.route('/tools')
@login_required
def tools_panel():
    clients = []
    if _MODULES_AVAILABLE:
        try:
            clients = get_ritual_module().list_clients()
        except Exception as e:
            logger.error("tools list_clients: %s", e)
    _audit('tools_view')
    return render_template('tools.html', clients=clients, site_base_url=SITE_BASE_URL)


# ─── Lab ───

@app.route('/lab')
@login_required
def lab_panel():
    lab_dir = WEBSITE_DIR / 'lab'
    groups = {'agent': [], 'demo': [], 'prototype': [], 'renewal': [], 'other': []}
    if lab_dir.exists():
        for entry in sorted(lab_dir.iterdir(), key=lambda e: e.stat().st_mtime, reverse=True):
            if entry.suffix != '.html':
                continue
            name = entry.name
            mtime = datetime.fromtimestamp(entry.stat().st_mtime).strftime('%Y-%m-%d')
            size_kb = round(entry.stat().st_size / 1024, 1)
            item = {'name': name, 'mtime': mtime, 'size_kb': size_kb,
                    'url': '%s/lab/%s' % (SITE_BASE_URL, name)}
            prefix = name.split('-')[0]
            if prefix in groups:
                groups[prefix].append(item)
            else:
                groups['other'].append(item)
    _audit('lab_view')
    return render_template('lab.html', groups=groups)


# ─── 서비스 헬스 ───

@app.route('/services')
@login_required
def services_panel():
    service_status = []
    for svc in SYSTEMD_SERVICES:
        status = _check_service_status(svc)
        service_status.append({'name': svc, 'status': status})

    env_keys = [
        'TELEGRAM_BOT_TOKEN', 'GEMINI_API_KEY',
        'ANTHROPIC_API_KEY', 'ADMIN_SECRET_KEY', 'SITE_BASE_URL',
    ]
    env_status = []
    for key in env_keys:
        val = os.getenv(key)
        env_status.append({'key': key, 'set': bool(val)})

    _audit('services_view')
    return render_template('services.html',
                           service_status=service_status,
                           env_status=env_status)


# ─── 설정 ───

@app.route('/settings')
@login_required
def settings_panel():
    _audit('settings_view')
    return render_template('settings.html', site_base_url=SITE_BASE_URL)


@app.route('/settings/password', methods=['POST'])
@login_required
def settings_password():
    global ADMIN_PASSWORD_HASH
    current = request.form.get('current', '')
    new_pw = request.form.get('new_password', '').strip()
    confirm = request.form.get('confirm', '').strip()

    if not check_password_hash(ADMIN_PASSWORD_HASH, current):
        flash('현재 비밀번호가 올바르지 않습니다.')
        return redirect(url_for('settings_panel'))

    if len(new_pw) < 8:
        flash('새 비밀번호는 8자 이상이어야 합니다.')
        return redirect(url_for('settings_panel'))

    if new_pw != confirm:
        flash('새 비밀번호가 일치하지 않습니다.')
        return redirect(url_for('settings_panel'))

    # 런타임 + 영속 파일 해시 동기화
    ADMIN_PASSWORD_HASH = generate_password_hash(new_pw, method='pbkdf2:sha256')
    _save_admin_password_hash(ADMIN_PASSWORD_HASH)
    _audit('password_changed')
    flash('비밀번호가 변경되어 영속 저장되었습니다.')
    return redirect(url_for('settings_panel'))


# ─── About Editor ───

@app.route('/about/edit', methods=['GET', 'POST'])
@login_required
def about_edit():
    about_path = WEBSITE_DIR / 'about' / 'index.html'
    error = None
    if request.method == 'POST':
        content = request.form.get('content', '')
        if not content.strip():
            error = '내용이 비어있습니다.'
        else:
            try:
                about_path.write_text(content, encoding='utf-8')
                _audit('about_edit')
                flash('어바웃 페이지가 저장되었습니다.')
                if request.form.get('publish'):
                    from core.admin.utils.git_publisher import publish_to_website
                    success, message = publish_to_website()
                    flash(message if success else f'저장은 완료, 발행 실패: {message}')
            except Exception as e:
                logger.error("about_edit write: %s", e)
                error = f'저장 실패: {e}'
    content = ''
    if about_path.exists():
        content = about_path.read_text(encoding='utf-8')
    return render_template('about_edit.html', content=content, error=error)


# ─── 에이전트 채팅 모니터 ───

# 에이전트 메타 (이름, 색상, 아이콘)
_AGENT_META = {
    'SA':          {'label': 'SA · 신호 분석',    'color': '#7A6E5A'},
    'CE':          {'label': 'CE · 편집장',       'color': '#4a4a4a'},
    'Gardener':    {'label': 'Gardener · 군집',   'color': '#8B7355'},
    'PlanCouncil': {'label': 'Plan Council',      'color': '#1B2D4F'},
    'Telegram':    {'label': 'Telegram · 입력',   'color': '#5a6a7a'},
    'HarnessDoctor':{'label': 'Harness Doctor',  'color': '#6a5a4a'},
    'System':      {'label': 'System',            'color': '#9a9a9a'},
}

_AGENT_JSONL_SOURCES = [
    ('web_work_history',       BASE_DIR / 'knowledge' / 'system' / 'web_work_history.jsonl'),
    ('plan_council_reports',   BASE_DIR / 'knowledge' / 'system' / 'plan_council_reports.jsonl'),
    ('evidence_log',           BASE_DIR / 'knowledge' / 'system' / 'evidence_log.jsonl'),
    ('harness_doctor_reports', BASE_DIR / 'knowledge' / 'system' / 'harness_doctor_reports.jsonl'),
]

def _parse_agent_events(limit: int = 80) -> list:
    """JSONL 소스에서 최근 이벤트를 에이전트 채팅 메시지로 변환."""
    events = []
    for source_key, path in _AGENT_JSONL_SOURCES:
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding='utf-8').strip().splitlines()
        except (IOError, OSError):
            continue
        for line in lines[-30:]:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts_raw = d.get('timestamp') or d.get('ts') or d.get('started_at') or ''
            ts_str = str(ts_raw)[:19].replace('T', ' ') if ts_raw else ''
            ts_sort = str(ts_raw)[:19] if ts_raw else ''

            if source_key == 'web_work_history':
                # 구조: {locked, agent, task, started_at, initial_state, final_state}
                agent = d.get('agent', 'System')
                task = str(d.get('task', ''))[:120]
                locked = d.get('locked', False)
                state = '작업 시작' if locked else '작업 완료'
                body = '%s — %s' % (state, task)
                events.append({'agent': agent, 'body': body, 'ts': ts_str, 'sort': ts_sort, 'source': source_key})

            elif source_key == 'plan_council_reports':
                # 구조: {timestamp, mode, task, claude, gemini, consensus}
                task = str(d.get('task', ''))[:80]
                consensus = d.get('consensus', {})
                status = consensus.get('status', d.get('status', ''))
                steps = consensus.get('steps', [])
                body = '[%s] %s' % (status, task)
                if steps:
                    body += '\n' + '\n'.join('• %s' % s for s in steps[:3])
                events.append({'agent': 'PlanCouncil', 'body': body, 'ts': ts_str, 'sort': ts_sort, 'source': source_key})

            elif source_key == 'evidence_log':
                # 구조: {timestamp, claim, evidence_type, source}
                claim = str(d.get('claim', ''))[:120]
                ev_type = d.get('evidence_type', '')
                body = '[%s] %s' % (ev_type, claim)
                events.append({'agent': 'System', 'body': body, 'ts': ts_str, 'sort': ts_sort, 'source': source_key})

            elif source_key == 'harness_doctor_reports':
                # 구조: {timestamp, score, overall, checks}
                score = d.get('score', '')
                overall = d.get('overall', '')
                checks = d.get('checks', [])
                body = 'Harness Doctor: %s (점수 %s)' % (overall, score)
                fails = [c.get('name', '') for c in checks if isinstance(c, dict) and c.get('status') == 'fail']
                if fails:
                    body += '\n' + '\n'.join('⚠ %s' % f for f in fails[:3])
                events.append({'agent': 'HarnessDoctor', 'body': body, 'ts': ts_str, 'sort': ts_sort, 'source': source_key})

    events.sort(key=lambda e: e.get('sort', ''), reverse=False)
    return events[-limit:]


@app.route('/agents')
@login_required
def agents_panel():
    events = _parse_agent_events(limit=80)
    source_stats = []
    for source_key, path in _AGENT_JSONL_SOURCES:
        if path.exists():
            try:
                count = len(path.read_text(encoding='utf-8').strip().splitlines())
            except Exception:
                count = 0
        else:
            count = 0
        source_stats.append({'key': source_key, 'count': count, 'exists': path.exists()})
    return render_template('agents.html', events=events, agent_meta=_AGENT_META, source_stats=source_stats)


@app.route('/api/agents/stream')
@login_required
def agents_stream():
    """SSE: 에이전트 이벤트 실시간 스트림 (1초 폴링)."""
    # 마지막으로 전송한 이벤트 개수 추적
    sent_count = [0]

    @stream_with_context
    def generate():
        while True:
            try:
                events = _parse_agent_events(limit=100)
                if sent_count[0] > len(events):
                    sent_count[0] = 0
                new_events = events[sent_count[0]:]
                if new_events:
                    for ev in new_events:
                        meta = _AGENT_META.get(ev['agent'], _AGENT_META['System'])
                        payload = {
                            'agent': ev['agent'],
                            'label': meta['label'],
                            'color': meta['color'],
                            'body': ev['body'],
                            'ts': ev['ts'],
                            'source': ev['source'],
                        }
                        yield 'data: %s\n\n' % json.dumps(payload, ensure_ascii=False)
                    sent_count[0] = len(events)
                else:
                    yield 'data: %s\n\n' % json.dumps({'type': 'heartbeat', 'ts': int(time.time())}, ensure_ascii=False)
            except GeneratorExit:
                break
            except Exception as e:
                logger.error("agents_stream error: %s", e)
            time.sleep(1)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'}
    )


# ─── B11: 에러 핸들러 ───
@app.errorhandler(400)
def bad_request(e):
    return jsonify({'error': '잘못된 요청'}), 400


@app.errorhandler(403)
def forbidden(e):
    return jsonify({'error': '접근 거부'}), 403


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': '없는 경로'}), 404
    return render_template(
        'dashboard.html',
        post_count=0,
        pipeline_count=0,
        signal_count=0,
        due_clients=[],
        growth_snapshot={},
        archive_board={'total': 0, 'published': 0, 'pending': 0, 'rows': []},
        today=datetime.now().strftime('%Y-%m-%d'),
        period=datetime.now().strftime('%Y-%m'),
    ), 404


@app.errorhandler(429)
def rate_limited(e):
    return jsonify({'error': '요청 과다. 잠시 후 다시 시도하세요.'}), 429


@app.errorhandler(Exception)
def handle_error(e):
    logger.error("unhandled error: %s", e, exc_info=True)
    if request.path.startswith('/api/'):
        return jsonify({'error': '내부 오류'}), 500
    return Response('Internal server error', status=500, mimetype='text/plain')


# ─── Helpers ───
def _load_index():
    index_path = ARCHIVE_DIR / 'index.json'
    if not index_path.exists():
        return []
    try:
        return json.loads(index_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, IOError):
        return []


def _count_pipeline_items():
    cached, hit = _cache_get('pipeline_count')
    if hit:
        return cached
    if not PUBLISHED_DIR.exists():
        return 0
    count = 0
    for date_dir in PUBLISHED_DIR.iterdir():
        if date_dir.is_dir():
            for item_dir in date_dir.iterdir():
                if item_dir.is_dir() and (item_dir / 'archive_essay.txt').exists():
                    count += 1
    _cache_set('pipeline_count', count)
    return count


def _load_pipeline_items():
    items = []
    if not PUBLISHED_DIR.exists():
        return items

    for date_dir in sorted(PUBLISHED_DIR.iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue
        for item_dir in sorted(date_dir.iterdir(), reverse=True):
            if not item_dir.is_dir():
                continue

            essay_path = item_dir / 'archive_essay.txt'
            caption_path = item_dir / 'instagram_caption.txt'
            meta_path = item_dir / 'meta.json'

            if not essay_path.exists():
                continue

            item = {
                'id': f"{date_dir.name}/{item_dir.name}",
                'date': date_dir.name,
                'essay': essay_path.read_text(encoding='utf-8')[:300],
                'caption': '',
                'meta': {}
            }

            if caption_path.exists():
                item['caption'] = caption_path.read_text(encoding='utf-8')
            if meta_path.exists():
                try:
                    item['meta'] = json.loads(meta_path.read_text(encoding='utf-8'))
                except (json.JSONDecodeError, IOError):
                    pass

            items.append(item)

    return items[:20]  # Latest 20


def _sanitize_slug(text):
    import re
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug[:60].strip('-')


def _allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ─── Run ───
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, debug=False, threaded=True)
