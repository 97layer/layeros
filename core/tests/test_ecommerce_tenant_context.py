"""
E-commerce tenant context regression tests.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def ecommerce_client(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-not-for-production")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ecommerce.db'}")
    monkeypatch.setenv("DEFAULT_TENANT_ID", "woohwahae")
    monkeypatch.setenv("REQUIRE_TENANT_HEADER", "false")
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("core.backend.ecommerce"):
            del sys.modules[mod_name]
    app_module = importlib.import_module("core.backend.ecommerce.main")
    with TestClient(app_module.app) as client:
        yield client


def test_root_sets_default_tenant_header(ecommerce_client):
    resp = ecommerce_client.get("/")
    assert resp.status_code == 200
    assert resp.headers.get("X-Tenant-ID") == "woohwahae"


def test_root_uses_requested_tenant_header(ecommerce_client):
    resp = ecommerce_client.get("/", headers={"X-Tenant-ID": "Acme_01"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Tenant-ID") == "acme_01"


def test_root_rejects_invalid_tenant_header(ecommerce_client):
    resp = ecommerce_client.get("/", headers={"X-Tenant-ID": "ACME!"})
    assert resp.status_code == 400
    assert "Invalid tenant id format" in resp.json()["detail"]


def test_token_roundtrip_preserves_tenant_claim(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-not-for-production")
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("core.backend.ecommerce"):
            del sys.modules[mod_name]
    auth_utils = importlib.import_module("core.backend.ecommerce.utils.auth")

    token = auth_utils.create_access_token(
        data={"sub": 7, "email": "user@example.com", "tenant_id": "acme"},
    )
    token_data = auth_utils.decode_access_token(token)
    assert token_data is not None
    assert token_data.user_id == 7
    assert token_data.tenant_id == "acme"


def test_authenticated_tenant_mismatch_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-not-for-production")
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("core.backend.ecommerce"):
            del sys.modules[mod_name]
    auth_utils = importlib.import_module("core.backend.ecommerce.utils.auth")
    token_data_cls = importlib.import_module("core.backend.ecommerce.schemas").TokenData
    token_data = token_data_cls(user_id=1, email="user@example.com", tenant_id="tenant_a")

    with pytest.raises(HTTPException) as exc:
        auth_utils.get_authenticated_tenant_id(
            token_data=token_data,
            requested_tenant_id="tenant_b",
        )

    assert exc.value.status_code == 403


def test_get_current_user_rejects_cross_tenant_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-not-for-production")
    monkeypatch.setenv("DEFAULT_TENANT_ID", "woohwahae")
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("core.backend.ecommerce"):
            del sys.modules[mod_name]

    auth_utils = importlib.import_module("core.backend.ecommerce.utils.auth")
    schemas_module = importlib.import_module("core.backend.ecommerce.schemas")

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return None

    class FakeDB:
        def query(self, *_args, **_kwargs):
            return FakeQuery()

    token_data = schemas_module.TokenData(
        user_id=10,
        email="tenant-b@example.com",
        tenant_id="tenant_a",
    )

    with pytest.raises(HTTPException) as exc:
        auth_utils.get_current_user(token_data=token_data, db=FakeDB())

    assert exc.value.status_code == 401
