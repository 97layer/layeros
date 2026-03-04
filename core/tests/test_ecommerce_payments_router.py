"""
E-commerce payment router regression tests.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def ecommerce_client(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-not-for-production")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ecommerce.db'}")
    monkeypatch.setenv(
        "PAYMENT_WEBHOOK_EVENT_CACHE_FILE",
        str(tmp_path / "payment_webhook_events.json"),
    )

    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("core.backend.ecommerce"):
            del sys.modules[mod_name]

    app_module = importlib.import_module("core.backend.ecommerce.main")
    with TestClient(app_module.app) as client:
        yield client, app_module


def test_payment_routes_registered(ecommerce_client):
    _, app_module = ecommerce_client
    paths = {route.path for route in app_module.app.router.routes}
    assert "/api/v1/payments/intent" in paths
    assert "/api/v1/payments/webhook" in paths
    assert "/api/v1/payments/orders/{order_id}" in paths


def test_payment_webhook_requires_signature(ecommerce_client):
    client, _ = ecommerce_client
    resp = client.post("/api/v1/payments/webhook", content=b"{}")
    assert resp.status_code == 400


def test_payment_webhook_fails_without_stripe_secret(ecommerce_client):
    client, _ = ecommerce_client
    resp = client.post(
        "/api/v1/payments/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=fake"},
    )
    assert resp.status_code == 503


def test_payment_webhook_idempotent_duplicate_event(ecommerce_client, monkeypatch):
    client, _ = ecommerce_client
    payments_module = importlib.import_module("core.backend.ecommerce.api.payments")
    payments_module._PROCESSED_WEBHOOK_EVENTS.clear()
    payments_module._PROCESSED_WEBHOOK_EVENT_ORDER.clear()

    fake_event = {
        "id": "evt_test_duplicate_1",
        "type": "payment_intent.succeeded",
        "data": {"object": {}},
    }
    monkeypatch.setattr(
        payments_module,
        "construct_webhook_event",
        lambda *_args, **_kwargs: fake_event,
    )

    first = client.post(
        "/api/v1/payments/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=fake"},
    )
    second = client.post(
        "/api/v1/payments/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=fake"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["idempotent"] is False
    assert second.json()["idempotent"] is True


def test_payment_webhook_idempotent_persists_after_reload(ecommerce_client, monkeypatch):
    client, _ = ecommerce_client
    payments_module = importlib.import_module("core.backend.ecommerce.api.payments")
    payments_module._PROCESSED_WEBHOOK_EVENTS.clear()
    payments_module._PROCESSED_WEBHOOK_EVENT_ORDER.clear()

    fake_event = {
        "id": "evt_test_persist_1",
        "type": "payment_intent.succeeded",
        "data": {"object": {}},
    }
    monkeypatch.setattr(
        payments_module,
        "construct_webhook_event",
        lambda *_args, **_kwargs: fake_event,
    )
    first = client.post(
        "/api/v1/payments/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=fake"},
    )
    assert first.status_code == 200
    assert first.json()["idempotent"] is False

    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("core.backend.ecommerce"):
            del sys.modules[mod_name]

    app_module = importlib.import_module("core.backend.ecommerce.main")
    new_payments_module = importlib.import_module("core.backend.ecommerce.api.payments")
    monkeypatch.setattr(
        new_payments_module,
        "construct_webhook_event",
        lambda *_args, **_kwargs: fake_event,
    )

    with TestClient(app_module.app) as reloaded_client:
        second = reloaded_client.post(
            "/api/v1/payments/webhook",
            content=b"{}",
            headers={"Stripe-Signature": "t=1,v1=fake"},
        )
    assert second.status_code == 200
    assert second.json()["idempotent"] is True


def test_payment_webhook_rolls_back_when_commit_fails(ecommerce_client, monkeypatch):
    client, _ = ecommerce_client
    payments_module = importlib.import_module("core.backend.ecommerce.api.payments")
    payments_module._PROCESSED_WEBHOOK_EVENTS.clear()
    payments_module._PROCESSED_WEBHOOK_EVENT_ORDER.clear()

    payment_intent_id = "pi_test_commit_fail_1"

    fake_event = {
        "id": "evt_test_commit_fail_1",
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": payment_intent_id}},
    }
    monkeypatch.setattr(
        payments_module,
        "construct_webhook_event",
        lambda *_args, **_kwargs: fake_event,
    )

    base_module = importlib.import_module("core.backend.ecommerce.models.base")
    probe_session = base_module.SessionLocal()
    session_cls = probe_session.__class__
    probe_session.close()

    rollback_called = {"value": False}
    original_rollback = session_cls.rollback

    class FakeOrder:
        payment_status = "pending"
        paid_at = None

    fake_order = FakeOrder()

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return fake_order

    def fake_query(self, *_args, **_kwargs):
        return FakeQuery()

    def failing_commit(self):
        raise RuntimeError("forced db failure")

    def tracking_rollback(self):
        rollback_called["value"] = True
        return original_rollback(self)

    monkeypatch.setattr(session_cls, "query", fake_query, raising=True)
    monkeypatch.setattr(session_cls, "commit", failing_commit, raising=True)
    monkeypatch.setattr(session_cls, "rollback", tracking_rollback, raising=True)

    resp = client.post(
        "/api/v1/payments/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=fake"},
    )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Database commit failed"
    assert rollback_called["value"] is True
    assert payments_module._is_processed_webhook_event(fake_event["id"]) is False
