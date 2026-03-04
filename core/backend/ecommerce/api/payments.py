"""Payment API endpoints (Stripe intent + webhook)."""

from __future__ import annotations

import json
import os
import threading
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models import Order, PaymentStatus, User, get_db
from ..services.payment import construct_webhook_event, create_payment_intent
from ..utils import get_current_active_admin, get_current_user

router = APIRouter(prefix="/payments", tags=["Payments"])
_logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_WEBHOOK_EVENT_CACHE_FILE = Path(
    os.getenv(
        "PAYMENT_WEBHOOK_EVENT_CACHE_FILE",
        str(_PROJECT_ROOT / "knowledge" / "system" / "payment_webhook_events.json"),
    )
)
_WEBHOOK_EVENT_CACHE_LIMIT = max(100, int(os.getenv("PAYMENT_WEBHOOK_EVENT_CACHE_LIMIT", "2000")))
_WEBHOOK_EVENT_LOCK = threading.Lock()
_PROCESSED_WEBHOOK_EVENTS: set[str] = set()
_PROCESSED_WEBHOOK_EVENT_ORDER: list[str] = []


def _commit_or_rollback(db: Session, *, context: str) -> None:
    """Commit DB changes and rollback on failure to keep session reusable."""
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        _logger.exception("database commit failed during %s", context)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database commit failed",
        ) from exc


def _load_processed_webhook_events() -> None:
    if not _WEBHOOK_EVENT_CACHE_FILE.exists():
        return
    try:
        payload = json.loads(_WEBHOOK_EVENT_CACHE_FILE.read_text(encoding="utf-8"))
        raw_events = payload.get("events", []) if isinstance(payload, dict) else []
        ordered = [str(item).strip() for item in raw_events if str(item).strip()]
        if len(ordered) > _WEBHOOK_EVENT_CACHE_LIMIT:
            ordered = ordered[-_WEBHOOK_EVENT_CACHE_LIMIT:]
        _PROCESSED_WEBHOOK_EVENT_ORDER.clear()
        _PROCESSED_WEBHOOK_EVENT_ORDER.extend(ordered)
        _PROCESSED_WEBHOOK_EVENTS.clear()
        _PROCESSED_WEBHOOK_EVENTS.update(ordered)
    except Exception as exc:
        _logger.warning("failed to load webhook idempotency cache: %s", exc)


def _persist_processed_webhook_events() -> None:
    payload = {
        "events": _PROCESSED_WEBHOOK_EVENT_ORDER[-_WEBHOOK_EVENT_CACHE_LIMIT:],
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    try:
        _WEBHOOK_EVENT_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = _WEBHOOK_EVENT_CACHE_FILE.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(_WEBHOOK_EVENT_CACHE_FILE)
    except Exception as exc:
        _logger.warning("failed to persist webhook idempotency cache: %s", exc)


def _mark_webhook_event_processed(event_id: str) -> None:
    if not event_id:
        return
    with _WEBHOOK_EVENT_LOCK:
        if event_id in _PROCESSED_WEBHOOK_EVENTS:
            return
        _PROCESSED_WEBHOOK_EVENTS.add(event_id)
        _PROCESSED_WEBHOOK_EVENT_ORDER.append(event_id)
        if len(_PROCESSED_WEBHOOK_EVENT_ORDER) > _WEBHOOK_EVENT_CACHE_LIMIT:
            overflow = len(_PROCESSED_WEBHOOK_EVENT_ORDER) - _WEBHOOK_EVENT_CACHE_LIMIT
            evicted = _PROCESSED_WEBHOOK_EVENT_ORDER[:overflow]
            del _PROCESSED_WEBHOOK_EVENT_ORDER[:overflow]
            for old_id in evicted:
                _PROCESSED_WEBHOOK_EVENTS.discard(old_id)
        _persist_processed_webhook_events()


def _is_processed_webhook_event(event_id: str) -> bool:
    if not event_id:
        return False
    with _WEBHOOK_EVENT_LOCK:
        return event_id in _PROCESSED_WEBHOOK_EVENTS


_load_processed_webhook_events()


class PaymentIntentCreate(BaseModel):
    order_id: int = Field(..., gt=0)


@router.post("/intent")
def create_intent(
    payload: PaymentIntentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create Stripe PaymentIntent for current user's order."""
    order = db.query(Order).filter(
        Order.id == payload.order_id,
        Order.user_id == current_user.id,
    ).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.payment_status == PaymentStatus.PAID.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order already paid")

    total = Decimal(order.total)
    amount = int(total)
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid order amount")

    try:
        idempotency_key = f"order-{order.id}-user-{current_user.id}-total-{amount}"
        intent = create_payment_intent(
            amount=amount,
            currency="krw",
            metadata={"order_id": str(order.id), "order_number": order.order_number},
            idempotency_key=idempotency_key,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except stripe.error.StripeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Stripe error: {exc.user_message or exc.code}") from exc

    order.payment_transaction_id = intent.id
    order.payment_gateway = "stripe"
    _commit_or_rollback(db, context="payment intent update")

    return {
        "order_id": order.id,
        "payment_intent_id": intent.id,
        "client_secret": intent.client_secret,
        "amount": amount,
        "currency": "krw",
        "status": order.payment_status,
    }


@router.get("/orders/{order_id}")
def get_payment_status(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == current_user.id,
    ).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return {
        "order_id": order.id,
        "payment_status": order.payment_status,
        "payment_gateway": order.payment_gateway,
        "payment_transaction_id": order.payment_transaction_id,
        "paid_at": order.paid_at,
    }


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe webhook endpoint."""
    body = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    if not sig_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe-Signature header")

    try:
        event = construct_webhook_event(body, sig_header)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid signature: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid payload: {exc}") from exc

    event_id = str(event.get("id", "")).strip()
    if _is_processed_webhook_event(event_id):
        return {"received": True, "idempotent": True}

    event_type = event.get("type")
    event_obj = event.get("data", {}).get("object", {})
    payment_intent_id = event_obj.get("id")
    if not payment_intent_id:
        _mark_webhook_event_processed(event_id)
        return {"received": True, "idempotent": False}

    order = db.query(Order).filter(Order.payment_transaction_id == payment_intent_id).first()
    if not order:
        _mark_webhook_event_processed(event_id)
        return {"received": True, "idempotent": False}

    if event_type == "payment_intent.succeeded":
        order.payment_status = PaymentStatus.PAID.value
        if not order.paid_at:
            order.paid_at = datetime.now(timezone.utc)
    elif event_type == "payment_intent.payment_failed":
        order.payment_status = PaymentStatus.FAILED.value

    _commit_or_rollback(db, context="stripe webhook update")
    _mark_webhook_event_processed(event_id)
    return {"received": True, "idempotent": False}


@router.post("/orders/{order_id}/mark-paid")
def mark_paid_manually(
    order_id: int,
    _: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db),
):
    """Admin fallback: mark payment as paid manually."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order.payment_status = PaymentStatus.PAID.value
    if not order.paid_at:
        order.paid_at = datetime.now(timezone.utc)
    _commit_or_rollback(db, context="manual paid fallback")
    db.refresh(order)
    return {
        "order_id": order.id,
        "payment_status": order.payment_status,
        "paid_at": order.paid_at,
    }
