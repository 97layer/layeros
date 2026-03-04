"""
LAYER OS 보안 테스트 픽스처
Flask CMS + FastAPI CMS 테스트 클라이언트 제공.
"""

import os
import sys
from pathlib import Path

import pytest

# 프로젝트 루트 등록
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# pytest 임시 디렉터리(/tmp) 쓰기 허용을 위해 guard 비활성화
os.environ.setdefault("LAYER_DISABLE_FILESYSTEM_GUARD", "1")

# 테스트 환경변수 — 실제 환경 오염 방지
_TEST_PASSWORD = 'test-password-2026'


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch):
    """모든 테스트에 필수 환경변수 주입."""
    from werkzeug.security import generate_password_hash
    pw_hash = generate_password_hash(_TEST_PASSWORD, method='pbkdf2:sha256')

    monkeypatch.setenv('FLASK_SECRET_KEY', 'test-secret-key-not-for-production')
    monkeypatch.setenv('FLASK_ADMIN_PASSWORD_HASH', pw_hash)
    monkeypatch.setenv('FASTAPI_ADMIN_PASSWORD_HASH', pw_hash)
    monkeypatch.setenv('CORS_ORIGINS', 'https://woohwahae.kr')
    monkeypatch.setenv('FASTAPI_CORS_ORIGINS', 'https://woohwahae.kr')


@pytest.fixture
def flask_client(_set_test_env):
    """Flask CMS 테스트 클라이언트."""
    # config 모듈은 backend/ 디렉토리에서 import하므로 path 조작 필요
    backend_dir = _PROJECT_ROOT / 'core' / 'backend'
    sys.path.insert(0, str(backend_dir))

    # 모듈 캐시에서 config 제거 (환경변수 재로드)
    for mod_name in list(sys.modules.keys()):
        if mod_name in ('config', 'core.backend.app', 'core.backend.config'):
            del sys.modules[mod_name]

    import importlib
    config = importlib.import_module('config')
    from core.backend.app import app

    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def fastapi_client(_set_test_env):
    """FastAPI CMS 테스트 클라이언트."""
    # 모듈 캐시에서 main 제거 (환경변수 재로드)
    for mod_name in list(sys.modules.keys()):
        if mod_name == 'core.backend.main':
            del sys.modules[mod_name]

    from fastapi.testclient import TestClient
    from core.backend.main import app
    with TestClient(app) as client:
        yield client


@pytest.fixture
def test_password():
    return _TEST_PASSWORD
