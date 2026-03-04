"""Base database models and session management."""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from ..config import settings

# Create engine
_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    connect_args=_connect_args,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base model
Base = declarative_base()


def get_db():
    """Database session dependency for FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
    _ensure_tenant_columns()


def _ensure_tenant_columns() -> None:
    """Backfill tenant columns for legacy databases without migrations."""
    inspector = inspect(engine)
    tables = {"users", "orders"}
    safe_default = settings.DEFAULT_TENANT_ID.replace("'", "''") or "woohwahae"
    with engine.begin() as conn:
        for table in tables:
            if table not in inspector.get_table_names():
                continue
            existing_columns = {col["name"] for col in inspector.get_columns(table)}
            if "tenant_id" in existing_columns:
                pass
            else:
                # SQLite/Postgres 모두 호환 가능한 형태로 추가.
                conn.execute(
                    text(
                        f"ALTER TABLE {table} "
                        f"ADD COLUMN tenant_id VARCHAR(64) NOT NULL DEFAULT '{safe_default}'"
                    )
                )
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table}_tenant_id ON {table} (tenant_id)"))
