"""Tenant context helpers for SaaS-ready request scoping."""

from __future__ import annotations

import re

from ..config import settings

_TENANT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


def normalize_tenant_id(raw: str) -> str:
    """Normalize and validate tenant identifier."""
    candidate = (raw or "").strip().lower()
    if not candidate:
        raise ValueError("Tenant id cannot be empty")
    if not _TENANT_PATTERN.fullmatch(candidate):
        raise ValueError(
            "Invalid tenant id format; use 2-63 chars of lowercase letters, digits, '_' or '-'"
        )
    return candidate


def resolve_public_tenant_id(header_value: str | None) -> str:
    """Resolve tenant id for public endpoints using header or default."""
    if header_value:
        return normalize_tenant_id(header_value)
    if settings.REQUIRE_TENANT_HEADER:
        raise ValueError(f"{settings.TENANT_HEADER} header required")
    return normalize_tenant_id(settings.DEFAULT_TENANT_ID)

