"""Application configuration.

Environment variables should be set in production:
- DATABASE_URL: PostgreSQL connection string
- REDIS_URL: Redis connection string
- JWT_SECRET_KEY: Secret key for JWT token signing
- STRIPE_API_KEY: Stripe API key
- TOSSPAYMENTS_SECRET_KEY: TossPayments secret key
- TOSSPAYMENTS_CLIENT_KEY: TossPayments client key
"""
import logging
import os
import secrets
from typing import Optional

logger = logging.getLogger(__name__)


def _debug_enabled() -> bool:
    return os.getenv("DEBUG", "False").lower() == "true"


def _load_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if secret:
        return secret
    if _debug_enabled():
        # Local debug fallback only.
        generated = secrets.token_urlsafe(48)
        logger.warning("JWT_SECRET_KEY missing in DEBUG mode; using ephemeral in-memory secret")
        return generated
    raise RuntimeError("JWT_SECRET_KEY environment variable is required")


class Settings:
    """Application settings."""

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./woohwahae_ecommerce.db"
    )

    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", None)

    # JWT
    JWT_SECRET_KEY: str = _load_jwt_secret()
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))

    # Payment Gateways
    STRIPE_API_KEY: str = os.getenv("STRIPE_API_KEY", "").strip()
    TOSSPAYMENTS_SECRET_KEY: str = os.getenv("TOSSPAYMENTS_SECRET_KEY", "").strip()
    TOSSPAYMENTS_CLIENT_KEY: str = os.getenv("TOSSPAYMENTS_CLIENT_KEY", "").strip()

    # Application
    APP_NAME: str = "WOOHWAHAE E-commerce"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    SQL_ECHO: bool = os.getenv("SQL_ECHO", "False").lower() == "true"
    DEFAULT_TENANT_ID: str = os.getenv("DEFAULT_TENANT_ID", "woohwahae").strip().lower()
    TENANT_HEADER: str = os.getenv("TENANT_HEADER", "X-Tenant-ID").strip()
    REQUIRE_TENANT_HEADER: bool = os.getenv("REQUIRE_TENANT_HEADER", "False").lower() == "true"

    # CORS
    CORS_ORIGINS: list = [
        "https://woohwahae.kr",
        "https://www.woohwahae.kr",
        "http://localhost:3000",
        "http://localhost:5173",
    ]


settings = Settings()
