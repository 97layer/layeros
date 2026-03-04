"""
Legacy cortex-admin(5001) 안정화 회귀 테스트.
"""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


def _load_admin_module(monkeypatch):
    pw_hash = generate_password_hash("test-admin-password-2026", method="pbkdf2:sha256")
    monkeypatch.setenv("ADMIN_SECRET_KEY", "test-admin-secret-key")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", pw_hash)
    monkeypatch.setenv("SITE_BASE_URL", "https://woohwahae.kr")

    if "core.admin.app" in sys.modules:
        del sys.modules["core.admin.app"]
    return importlib.import_module("core.admin.app")


@pytest.fixture
def admin_module(monkeypatch):
    return _load_admin_module(monkeypatch)


@pytest.fixture
def admin_client(admin_module):
    app = admin_module.app
    app.config["TESTING"] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["_csrf_token"] = "csrf-test-token"
        yield client


def test_login_rate_limit_prunes_stale_attempts(admin_module):
    ip = "127.0.0.1"
    now_ts = time.time()
    admin_module._login_attempts[ip] = [
        now_ts - admin_module.LOGIN_WINDOW_SECONDS - 1
    ] * admin_module.LOGIN_MAX_ATTEMPTS

    assert admin_module._is_login_limited(ip) is False


def test_command_api_rejects_non_object_params(admin_client):
    resp = admin_client.post(
        "/api/command",
        json={"action": "inject_signal", "params": "not-an-object"},
        headers={"X-CSRF-Token": "csrf-test-token"},
    )

    assert resp.status_code == 400
    assert "params" in resp.get_json()["error"]


def test_service_add_invalid_price_returns_redirect(admin_client):
    resp = admin_client.post(
        "/service/add",
        data={
            "_csrf_token": "csrf-test-token",
            "name": "Test Service",
            "category": "service",
            "price": "not-a-number",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith("/service")


def test_non_api_error_handler_returns_500(admin_module):
    app = admin_module.app
    with app.test_request_context("/dashboard"):
        resp = admin_module.handle_error(RuntimeError("boom"))
    assert resp.status_code == 500
