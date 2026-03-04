"""
WOOHWAHAE CMS Backend Configuration
Flask-based backend — 보안 강화 버전
"""

import os
import sys
from pathlib import Path

# core.system 접근
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from core.system.security import require_env, hash_password

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / '.env')
except ImportError:
    pass

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = BASE_DIR / "archive"
ARCHIVE_JSON = ARCHIVE_DIR / "index.json"
UPLOADS_DIR = BASE_DIR / "assets" / "uploads"

# Ensure directories exist
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Flask config — fallback 없음, 환경변수 필수
SECRET_KEY = require_env('FLASK_SECRET_KEY')
DEBUG = False

# Authentication — 우선순위: FLASK_ADMIN_PASSWORD_HASH → ADMIN_PASSWORD_HASH(legacy)
_admin_hash = os.getenv('FLASK_ADMIN_PASSWORD_HASH') or os.getenv('ADMIN_PASSWORD_HASH')
if not _admin_hash:
    raise RuntimeError("FLASK_ADMIN_PASSWORD_HASH 또는 ADMIN_PASSWORD_HASH 환경변수 필수. .env에 설정하세요.")
ADMIN_PASSWORD_HASH = _admin_hash

# Content settings
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

# CORS settings — 허용 오리진 명시
CORS_ORIGINS = os.getenv(
    'CORS_ORIGINS',
    'https://woohwahae.kr'
).split(',')

# Audit log path
AUDIT_LOG_FILE = _PROJECT_ROOT / 'knowledge' / 'reports' / 'cms_audit.log'
