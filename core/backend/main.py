#!/usr/bin/env python3
"""
WOOHWAHAE CMS Backend
FastAPI 인라인 텍스트 편집 시스템 — 보안 강화 버전
"""

import os
import sys
import time
import json
import importlib
import subprocess
from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from anyio import to_thread
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from pydantic import BaseModel, Field

try:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token
except ImportError:
    google_requests = None
    google_id_token = None

# LAYER OS core modules
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from core.system.security import (
    require_env,
    verify_password,
    generate_token,
    sanitize_html_field,
    load_cors_origins,
    SecurityHeadersMiddleware,
    setup_audit_logger,
    RateLimiter,
)
from core.system.queue_manager import QueueManager

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / '.env')
except ImportError:
    pass


class WSGIAdapter:
    """Minimal ASGI-to-WSGI adapter to avoid deprecated middleware imports."""

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _build_environ(scope: dict[str, Any], body: bytes) -> dict[str, Any]:
        environ: dict[str, Any] = {
            "REQUEST_METHOD": scope["method"],
            "SCRIPT_NAME": scope.get("root_path", ""),
            "PATH_INFO": scope.get("path", ""),
            "QUERY_STRING": scope.get("query_string", b"").decode("latin-1"),
            "SERVER_PROTOCOL": "HTTP/%s" % scope.get("http_version", "1.1"),
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": scope.get("scheme", "http"),
            "wsgi.input": BytesIO(body),
            "wsgi.errors": sys.stderr,
            "wsgi.multithread": True,
            "wsgi.multiprocess": True,
            "wsgi.run_once": False,
            "CONTENT_LENGTH": str(len(body)),
        }
        server = scope.get("server")
        if server:
            environ["SERVER_NAME"] = server[0]
            environ["SERVER_PORT"] = str(server[1])
        client = scope.get("client")
        if client:
            environ["REMOTE_ADDR"] = client[0]

        for raw_name, raw_value in scope.get("headers", []):
            name = raw_name.decode("latin-1").upper().replace("-", "_")
            value = raw_value.decode("latin-1")
            if name == "CONTENT_TYPE":
                environ["CONTENT_TYPE"] = value
            elif name == "CONTENT_LENGTH":
                environ["CONTENT_LENGTH"] = value
            else:
                environ[f"HTTP_{name}"] = value
        return environ

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        if scope["type"] != "http":
            await send({"type": "http.response.start", "status": 500, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return

        body = b""
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break

        environ = self._build_environ(scope, body)
        response_chunks: list[bytes] = []
        status_code = 500
        response_headers: list[tuple[bytes, bytes]] = []

        def start_response(status: str, headers: list[tuple[str, str]], exc_info=None):
            nonlocal status_code, response_headers
            status_code = int(status.split(" ", 1)[0])
            response_headers = [
                (key.encode("latin-1"), value.encode("latin-1"))
                for key, value in headers
            ]
            return response_chunks.append

        def run_wsgi():
            result = self.app(environ, start_response)
            try:
                for chunk in result:
                    if chunk:
                        response_chunks.append(chunk)
            finally:
                if hasattr(result, "close"):
                    result.close()

        await to_thread.run_sync(run_wsgi)

        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": response_headers,
        })

        if not response_chunks:
            await send({"type": "http.response.body", "body": b""})
            return

        last_index = len(response_chunks) - 1
        for index, chunk in enumerate(response_chunks):
            await send({
                "type": "http.response.body",
                "body": chunk,
                "more_body": index < last_index,
            })

# ─── 환경변수 (fallback 없음) ─────────────────────────────────

ADMIN_PASSWORD_HASH = require_env('FASTAPI_ADMIN_PASSWORD_HASH')


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_ALLOWED_HD = os.getenv("GOOGLE_OAUTH_ALLOWED_HD", "").strip()
USER_SESSION_TTL = max(300, _env_int("FASTAPI_USER_SESSION_TTL", 86400))
GOOGLE_CLOCK_SKEW_SECONDS = max(0, _env_int("GOOGLE_OAUTH_CLOCK_SKEW", 30))
GOOGLE_OAUTH_READY = bool(
    GOOGLE_OAUTH_CLIENT_ID and google_requests is not None and google_id_token is not None
)

# ─── FastAPI 앱 ───────────────────────────────────────────────

app = FastAPI(
    title="WOOHWAHAE CMS",
    version="1.0.0",
    docs_url=None,   # Swagger UI 비활성화 (프로덕션)
    redoc_url=None,   # ReDoc 비활성화
)

# 보안 헤더 미들웨어 (CORS보다 먼저 등록 = 나중에 실행)
app.add_middleware(SecurityHeadersMiddleware)

# CORS — 허용 오리진 명시, 메서드/헤더 제한
_cors_origins = load_cors_origins(default=["https://woohwahae.kr"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# ─── 감사 로거 ────────────────────────────────────────────────

_audit_log_path = _PROJECT_ROOT / 'knowledge' / 'reports' / 'fastapi_audit.log'
_audit_logger = setup_audit_logger('fastapi_audit', _audit_log_path)

# 로그인 레이트 리미터 (5회/분)
_login_limiter = RateLimiter(max_requests=5, window_seconds=60)
_oauth_login_limiter = RateLimiter(max_requests=20, window_seconds=60)


def _audit(request: Request, action: str, detail: str = '') -> None:
    ip = request.client.host if request.client else 'unknown'
    _audit_logger.info("ip=%s action=%s detail=%s", ip, action, detail)


_ALLOWED_QUEUE_AGENTS = {"SA", "AD", "CE", "CD", "Ralph"}

_MOUNT_STATUS: dict[str, dict[str, Any]] = {
    "cms": {"path": "/cms", "mounted": False, "error": ""},
    "upload": {"path": "/upload", "mounted": False, "error": ""},
    "commerce": {"path": "/commerce", "mounted": False, "error": ""},
}


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def _is_process_running(pattern: str) -> bool:
    """
    운영 상태 확인용 최소 프로세스 체크.
    pgrep 결과에 현재 PID만 있는 경우는 제외한다.
    """
    try:
        proc = subprocess.run(
            ["pgrep", "-f", pattern],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False

    if proc.returncode != 0 or not proc.stdout.strip():
        return False

    current_pid = str(os.getpid())
    for pid in proc.stdout.splitlines():
        if pid.strip() and pid.strip() != current_pid:
            return True
    return False


def _queue_counts() -> dict[str, int]:
    tasks_root = _PROJECT_ROOT / '.infra' / 'queue' / 'tasks'
    counts: dict[str, int] = {}
    for state in ('pending', 'processing', 'completed'):
        state_dir = tasks_root / state
        counts[state] = len(list(state_dir.glob('*.json'))) if state_dir.exists() else 0
    return counts


def _queue_pending_summary(limit: int = 50) -> list[dict[str, str]]:
    queue = QueueManager()
    tasks = queue.get_pending_tasks()
    tasks = sorted(tasks, key=lambda t: t.created_at, reverse=True)

    summary: list[dict[str, str]] = []
    for task in tasks[:limit]:
        summary.append(
            {
                "task_id": task.task_id,
                "agent_type": task.agent_type,
                "task_type": task.task_type,
                "created_at": task.created_at,
            }
        )
    return summary


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_z() -> str:
    return _utcnow().isoformat().replace("+00:00", "Z")


def _load_plan_council_meta() -> dict[str, Any]:
    report_path = _PROJECT_ROOT / 'knowledge' / 'system' / 'plan_council_reports.jsonl'
    if not report_path.exists():
        return {"status": "unknown"}

    try:
        last_line = report_path.read_text(encoding='utf-8').strip().splitlines()[-1]
        payload = json.loads(last_line)
    except Exception:
        return {"status": "unknown"}

    consensus = payload.get('consensus', {})
    return {
        "status": consensus.get('status', 'unknown'),
        "models_used": consensus.get('models_used', []),
        "timestamp": payload.get('timestamp'),
    }


def _mount_subapps() -> None:
    mounts = (
        ("cms", "/cms", "core.backend.app", True),
        ("upload", "/upload", "core.backend.photo_upload", False),
        ("commerce", "/commerce", "core.backend.ecommerce.main", False),
    )
    for name, mount_path, module_path, is_wsgi in mounts:
        try:
            module = importlib.import_module(module_path)
            mounted_app = getattr(module, 'app')
            app.mount(
                mount_path,
                WSGIAdapter(mounted_app) if is_wsgi else mounted_app,
                name=name,
            )
            _MOUNT_STATUS[name]["mounted"] = True
            _MOUNT_STATUS[name]["error"] = ""
        except Exception as exc:
            _MOUNT_STATUS[name]["mounted"] = False
            _MOUNT_STATUS[name]["error"] = str(exc)


_mount_subapps()


# ─── 데이터베이스 ─────────────────────────────────────────────

DATABASE_URL = os.getenv("FASTAPI_DATABASE_URL", "sqlite:///./woohwahae_cms.db")
_db_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_db_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Content(Base):
    __tablename__ = "contents"
    id = Column(Integer, primary_key=True, index=True)
    page = Column(String(100), index=True)
    element_id = Column(String(200), index=True)
    content = Column(Text)
    updated_at = Column(DateTime, default=_utcnow)


Base.metadata.create_all(bind=engine)


# ─── Pydantic 모델 (길이 제한) ────────────────────────────────

class ContentUpdate(BaseModel):
    page: str = Field(..., max_length=100)
    element_id: str = Field(..., max_length=200)
    content: str = Field(..., max_length=50000)


class ContentResponse(BaseModel):
    id: int
    page: str
    element_id: str
    content: str
    updated_at: datetime


class AdminAuth(BaseModel):
    password: str = Field(..., max_length=200)


class QueueTaskCreate(BaseModel):
    agent_type: str = Field(..., min_length=2, max_length=16)
    task_type: str = Field(..., min_length=2, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)


class GoogleOAuthLoginPayload(BaseModel):
    credential: str = Field(..., min_length=32, max_length=8192)


# ─── 세션/토큰 ────────────────────────────────────────────────

# {token: {'created': timestamp}} — secrets 기반, 1시간 만료
_admin_sessions: dict[str, dict] = {}
SESSION_TTL = 3600  # 1시간
_user_sessions: dict[str, dict[str, Any]] = {}


def _cleanup_expired_sessions() -> None:
    now = time.time()
    expired = [t for t, v in _admin_sessions.items() if now - v['created'] > SESSION_TTL]
    for t in expired:
        del _admin_sessions[t]

    expired_user_tokens = [t for t, v in _user_sessions.items() if now - v['created'] > USER_SESSION_TTL]
    for t in expired_user_tokens:
        del _user_sessions[t]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _extract_bearer_token(request: Request) -> str:
    auth = request.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return ""


def _extract_admin_token(request: Request) -> str:
    token = _extract_bearer_token(request)
    if token:
        return token
    return request.headers.get("x-admin-token", "").strip()


def _extract_user_token(request: Request) -> str:
    token = _extract_bearer_token(request)
    if token:
        return token
    return request.headers.get("x-user-token", "").strip()


def check_admin(request: Request):
    """관리자 권한 확인 — Authorization Bearer 토큰 + 만료 검증."""
    _cleanup_expired_sessions()
    token = _extract_admin_token(request)
    if not token or token not in _admin_sessions:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


def _user_payload_from_google_claims(claims: dict[str, Any]) -> dict[str, Any]:
    return {
        "sub": str(claims.get("sub", "")),
        "email": str(claims.get("email", "")).strip().lower(),
        "name": str(claims.get("name", "")).strip(),
        "picture": str(claims.get("picture", "")).strip(),
    }


def _build_google_oauth_config() -> dict[str, Any]:
    return {
        "enabled": GOOGLE_OAUTH_READY,
        "provider": "google",
        "client_id": GOOGLE_OAUTH_CLIENT_ID if GOOGLE_OAUTH_READY else "",
        "reason": "" if GOOGLE_OAUTH_READY else "GOOGLE_OAUTH_CLIENT_ID or google-auth dependency missing",
    }


def _current_user_from_request(request: Request) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    _cleanup_expired_sessions()
    token = _extract_user_token(request)
    if not token:
        return None, None
    session = _user_sessions.get(token)
    if not session:
        return token, None
    return token, session


# ─── 인증 엔드포인트 ──────────────────────────────────────────

@app.post("/api/admin/login")
async def admin_login(auth: AdminAuth, request: Request):
    ip = request.client.host if request.client else 'unknown'

    if _login_limiter.is_limited(ip):
        _audit(request, 'login_rate_limited', ip)
        raise HTTPException(status_code=429, detail="Too many attempts. Try later.")

    if not verify_password(auth.password, ADMIN_PASSWORD_HASH):
        _audit(request, 'login_failed', ip)
        raise HTTPException(status_code=401, detail="Invalid password")

    _login_limiter.reset(ip)
    token = generate_token(32)
    _admin_sessions[token] = {'created': time.time()}
    _audit(request, 'login_success', ip)
    return {"token": token, "message": "Login successful"}


@app.get("/api/auth/google/config")
async def google_auth_config():
    return _build_google_oauth_config()


@app.post("/api/auth/google/login")
async def google_auth_login(payload: GoogleOAuthLoginPayload, request: Request):
    if not GOOGLE_OAUTH_READY:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")

    ip = request.client.host if request.client else 'unknown'
    if _oauth_login_limiter.is_limited(ip):
        _audit(request, 'oauth_login_rate_limited', ip)
        raise HTTPException(status_code=429, detail="Too many attempts. Try later.")

    try:
        token_info = google_id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            GOOGLE_OAUTH_CLIENT_ID,
            clock_skew_in_seconds=GOOGLE_CLOCK_SKEW_SECONDS,
        )
    except ValueError:
        _audit(request, 'oauth_login_failed', 'google_token_invalid')
        raise HTTPException(status_code=401, detail="Invalid Google credential")

    issuer = str(token_info.get("iss", ""))
    if issuer not in ("accounts.google.com", "https://accounts.google.com"):
        _audit(request, 'oauth_login_failed', 'issuer_invalid')
        raise HTTPException(status_code=401, detail="Invalid token issuer")

    if not token_info.get("email_verified"):
        _audit(request, 'oauth_login_failed', 'email_not_verified')
        raise HTTPException(status_code=401, detail="Email is not verified")

    if GOOGLE_OAUTH_ALLOWED_HD:
        hosted_domain = str(token_info.get("hd", "")).strip().lower()
        if hosted_domain != GOOGLE_OAUTH_ALLOWED_HD.lower():
            _audit(request, 'oauth_login_failed', 'hosted_domain_mismatch')
            raise HTTPException(status_code=403, detail="Google hosted domain is not allowed")

    user = _user_payload_from_google_claims(token_info)
    if not user["sub"] or not user["email"]:
        _audit(request, 'oauth_login_failed', 'missing_claims')
        raise HTTPException(status_code=401, detail="Required Google claims are missing")

    session_token = generate_token(32)
    _user_sessions[session_token] = {
        "created": time.time(),
        "user": user,
    }
    _oauth_login_limiter.reset(ip)
    _audit(request, 'oauth_login_success', user["email"])
    return {
        "token": session_token,
        "user": user,
        "expires_in": USER_SESSION_TTL,
        "provider": "google",
    }


@app.get("/api/auth/me")
async def auth_me(request: Request):
    _, session = _current_user_from_request(request)
    if not session:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user": session["user"],
        "expires_in": USER_SESSION_TTL,
    }


@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    token, session = _current_user_from_request(request)
    if token and session:
        _user_sessions.pop(token, None)
    return {"success": True}


# ─── API 엔드포인트 ───────────────────────────────────────────

@app.get("/api/contents/{page}")
async def get_page_contents(page: str, request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    if len(page) > 100:
        raise HTTPException(status_code=400, detail="Page name too long")
    contents = db.query(Content).filter(Content.page == page).all()
    return contents


@app.get("/api/content/{page}/{element_id}")
async def get_content(page: str, element_id: str, request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    if len(page) > 100 or len(element_id) > 200:
        raise HTTPException(status_code=400, detail="Input too long")
    content = db.query(Content).filter(
        Content.page == page,
        Content.element_id == element_id
    ).first()

    if not content:
        return {"content": None}

    return {
        "content": content.content,
        "updated_at": content.updated_at
    }


@app.post("/api/content/update")
async def update_content(
    data: ContentUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    check_admin(request)

    # XSS 방어
    safe_content = sanitize_html_field(data.content)
    safe_page = sanitize_html_field(data.page)
    safe_element = sanitize_html_field(data.element_id)

    content = db.query(Content).filter(
        Content.page == safe_page,
        Content.element_id == safe_element
    ).first()

    if content:
        content.content = safe_content
        content.updated_at = _utcnow()
    else:
        content = Content(
            page=safe_page,
            element_id=safe_element,
            content=safe_content
        )
        db.add(content)

    db.commit()
    db.refresh(content)

    _audit(request, 'content_update', "%s/%s" % (safe_page, safe_element))
    return {
        "success": True,
        "content": content.content,
        "updated_at": content.updated_at
    }


@app.get("/api/pages")
async def get_all_pages(request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    pages = db.query(Content.page).distinct().all()
    return [p[0] for p in pages]


@app.get("/healthz")
async def healthz():
    queue_counts = _queue_counts()
    orchestrator_running = _is_process_running("core/system/pipeline_orchestrator.py")
    lock_state = _read_json(
        _PROJECT_ROOT / "knowledge" / "system" / "web_work_lock.json",
        {"locked": None},
    )

    status = "ok"
    if not orchestrator_running or any(not svc["mounted"] for svc in _MOUNT_STATUS.values()):
        status = "degraded"

    return {
        "status": status,
        "timestamp": _utcnow_z(),
        "gateway": {"name": "fastapi-main", "version": "1.1.0"},
        "services": _MOUNT_STATUS,
        "queue": queue_counts,
        "orchestrator": {"running": orchestrator_running},
        "work_lock": lock_state,
        "plan_council": _load_plan_council_meta(),
    }


@app.get("/harness/status")
async def harness_status():
    pending = _queue_pending_summary(limit=50)
    return {
        "status": "ok",
        "timestamp": _utcnow_z(),
        "queue": {
            "counts": _queue_counts(),
            "pending": pending,
        },
        "orchestrator": {
            "running": _is_process_running("core/system/pipeline_orchestrator.py"),
        },
        "mounts": _MOUNT_STATUS,
        "plan_council": _load_plan_council_meta(),
    }


@app.get("/status")
async def status_alias():
    return await harness_status()


@app.get("/queue/pending")
async def queue_pending(limit: int = 100):
    safe_limit = max(1, min(limit, 500))
    pending = _queue_pending_summary(limit=safe_limit)
    return {
        "count": len(pending),
        "totals": _queue_counts(),
        "items": pending,
    }


@app.post("/queue/task")
async def queue_task_create(
    data: QueueTaskCreate,
    request: Request,
):
    check_admin(request)

    if data.agent_type not in _ALLOWED_QUEUE_AGENTS:
        raise HTTPException(status_code=400, detail="Unsupported agent_type")

    task_type = sanitize_html_field(data.task_type).strip()
    if not task_type:
        raise HTTPException(status_code=400, detail="Invalid task_type")

    queue = QueueManager()
    task_id = queue.create_task(
        agent_type=data.agent_type,
        task_type=task_type,
        payload=data.payload,
    )
    _audit(request, "queue_task_create", f"{data.agent_type}/{task_type}:{task_id}")

    return {
        "success": True,
        "task_id": task_id,
    }


@app.get("/api/admin/overview")
async def admin_overview(
    request: Request,
):
    check_admin(request)

    health = await healthz()
    harness = await harness_status()

    with SessionLocal() as db:
        pages = db.query(Content.page).distinct().all()

    return {
        "timestamp": _utcnow_z(),
        "health": health,
        "harness": harness,
        "pages": [p[0] for p in pages],
        "endpoints": {
            "healthz": "/healthz",
            "harness_status": "/harness/status",
            "queue_pending": "/queue/pending",
            "cms_root": "/cms/",
            "upload_root": "/upload/",
            "commerce_root": "/commerce/",
        },
    }


# ─── 관리자 패널 ──────────────────────────────────────────────

# Keep both routes to avoid /admin <-> /admin/ redirect loops behind nginx.
@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/", response_class=HTMLResponse)
async def admin_panel():
    return """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WOOHWAHAE Control Plane</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif; background: #f1f1f1; padding: 24px; color: #181818; }
        .container { max-width: 1280px; margin: 0 auto; background: white; padding: 28px; border-radius: 12px; box-shadow: 0 2px 18px rgba(0,0,0,0.08); }
        h1 { font-size: 26px; margin-bottom: 16px; color: #222; }
        h2 { font-size: 18px; margin-bottom: 14px; color: #222; }
        .login-form { max-width: 400px; margin: 100px auto; }
        input[type="password"], input[type="text"], textarea, select {
            width: 100%;
            padding: 10px;
            font-size: 14px;
            border: 1px solid #d7d7d7;
            border-radius: 6px;
            margin-bottom: 10px;
            background: #fff;
        }
        textarea { min-height: 84px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
        button { background: #111; color: white; padding: 10px 14px; font-size: 14px; border: none; border-radius: 6px; cursor: pointer; }
        button:hover { background: #333; }
        .admin-panel { display: none; }
        .admin-panel.active { display: block; }
        .toolbar { margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
        .toolbar button.secondary { background: #4b5563; }
        .grid { display: grid; grid-template-columns: 1fr; gap: 20px; }
        .card { border: 1px solid #e4e4e4; border-radius: 10px; padding: 16px; background: #fafafa; }
        .metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
        .metric { background: #fff; border: 1px solid #e9e9e9; border-radius: 8px; padding: 10px; }
        .metric .k { font-size: 12px; color: #666; margin-bottom: 4px; }
        .metric .v { font-size: 16px; font-weight: 600; color: #1f2937; word-break: break-word; }
        .quick-links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; }
        .quick-links a { color: #0f4ea8; text-decoration: none; font-size: 13px; }
        .quick-links a:hover { text-decoration: underline; }
        .status-chip { display: inline-block; font-size: 12px; padding: 4px 8px; border-radius: 999px; color: #fff; background: #6b7280; }
        .status-chip.ok { background: #16a34a; }
        .status-chip.degraded { background: #d97706; }
        .status-chip.fail { background: #dc2626; }
        .json-box { background: #111827; color: #f3f4f6; border-radius: 8px; padding: 12px; font-size: 12px; overflow: auto; max-height: 280px; }
        .page-selector { margin-bottom: 14px; display: flex; gap: 10px; align-items: center; }
        .page-selector select { margin-bottom: 0; max-width: 240px; }
        .content-editor { margin-top: 10px; }
        .editable-item { background: #f9f9f9; padding: 20px; margin-bottom: 20px; border-radius: 4px; border: 1px solid #e0e0e0; }
        .editable-item h3 { font-size: 14px; color: #666; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px; }
        .editable-item textarea { width: 100%; padding: 12px; font-size: 15px; border: 1px solid #ddd; border-radius: 4px; min-height: 100px; font-family: inherit; resize: vertical; margin-bottom: 0; }
        .save-btn { background: #4CAF50; margin-top: 10px; }
        .status { margin-left: 10px; padding: 5px 10px; border-radius: 3px; font-size: 14px; display: inline-block; }
        .status.success { background: #d4edda; color: #155724; }
        .status.error { background: #f8d7da; color: #721c24; }
        .inline-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .label { font-size: 13px; color: #555; margin-bottom: 6px; display: block; }
        @media (max-width: 900px) {
            .metrics { grid-template-columns: 1fr; }
            .inline-row { grid-template-columns: 1fr; }
            .page-selector { flex-direction: column; align-items: flex-start; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>WOOHWAHAE Control Plane</h1>
        <div id="loginForm" class="login-form">
            <h2>관리자 로그인</h2>
            <input type="password" id="password" placeholder="비밀번호 입력">
            <button onclick="login()">로그인</button>
        </div>
        <div id="adminPanel" class="admin-panel">
            <div class="toolbar">
                <button onclick="loadSystemStatus()">운영 상태 새로고침</button>
                <button class="secondary" onclick="loadPageContent()">콘텐츠 다시 불러오기</button>
                <span id="globalStatus" class="status-chip">idle</span>
            </div>

            <div class="grid">
                <section class="card">
                    <h2>운영 대시보드</h2>
                    <div class="metrics">
                        <div class="metric"><div class="k">Gateway</div><div class="v" id="mGateway">-</div></div>
                        <div class="metric"><div class="k">Orchestrator</div><div class="v" id="mOrchestrator">-</div></div>
                        <div class="metric"><div class="k">Plan Council</div><div class="v" id="mPlan">-</div></div>
                    </div>
                    <div class="metrics">
                        <div class="metric"><div class="k">Queue Pending</div><div class="v" id="qPending">0</div></div>
                        <div class="metric"><div class="k">Queue Processing</div><div class="v" id="qProcessing">0</div></div>
                        <div class="metric"><div class="k">Queue Completed</div><div class="v" id="qCompleted">0</div></div>
                    </div>
                    <div class="quick-links" id="quickLinks"></div>
                    <p style="font-size:12px;color:#666;margin-top:10px;">Mounted Services</p>
                    <pre class="json-box" id="mountJson">{}</pre>
                </section>

                <section class="card">
                    <h2>작업 큐 주입</h2>
                    <div class="inline-row">
                        <div>
                            <label class="label" for="taskAgent">Agent</label>
                            <select id="taskAgent">
                                <option value="SA">SA</option>
                                <option value="AD">AD</option>
                                <option value="CE">CE</option>
                                <option value="CD">CD</option>
                                <option value="Ralph">Ralph</option>
                            </select>
                        </div>
                        <div>
                            <label class="label" for="taskType">Task Type</label>
                            <input type="text" id="taskType" value="analyze_signal">
                        </div>
                    </div>
                    <label class="label" for="taskPayload">Payload(JSON)</label>
                    <textarea id="taskPayload">{\"source\":\"admin_console\"}</textarea>
                    <button onclick="createQueueTask()">큐 등록</button>
                    <span id="taskStatus" class="status"></span>
                </section>

                <section class="card">
                    <h2>콘텐츠 편집</h2>
                    <div class="page-selector">
                        <label class="label" for="pageSelect" style="margin:0;">페이지:</label>
                        <select id="pageSelect" onchange="loadPageContent()">
                            <option value="">페이지를 선택하세요</option>
                            <option value="index">메인 페이지</option>
                            <option value="about">About</option>
                            <option value="practice">Practice</option>
                        </select>
                        <button onclick="openPage()">페이지 미리보기</button>
                    </div>
                    <div id="contentEditor" class="content-editor"></div>
                </section>
            </div>
        </div>
    </div>
    <script>
        let adminToken = sessionStorage.getItem('adminToken');
        if (adminToken) showAdminPanel();

        async function login() {
            const password = document.getElementById('password').value;
            try {
                const response = await fetch('/api/admin/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({password})
                });
                if (response.ok) {
                    const data = await response.json();
                    adminToken = data.token;
                    sessionStorage.setItem('adminToken', adminToken);
                    showAdminPanel();
                } else if (response.status === 429) {
                    alert('너무 많은 시도. 잠시 후 다시 시도하세요.');
                } else {
                    alert('비밀번호가 틀렸습니다.');
                }
            } catch (error) {
                alert('로그인 중 오류가 발생했습니다.');
            }
        }

        function showAdminPanel() {
            document.getElementById('loginForm').style.display = 'none';
            document.getElementById('adminPanel').classList.add('active');
            loadSystemStatus();
        }

        function setGlobalStatus(text, level) {
            const el = document.getElementById('globalStatus');
            el.textContent = text;
            el.className = 'status-chip ' + (level || '');
        }

        function authHeaders(extra) {
            const base = {'Authorization': 'Bearer ' + adminToken};
            return Object.assign(base, extra || {});
        }

        async function loadSystemStatus() {
            if (!adminToken) return;
            setGlobalStatus('loading', '');
            try {
                const response = await fetch('/api/admin/overview', {
                    headers: authHeaders()
                });
                if (!response.ok) {
                    throw new Error('status load failed');
                }
                const data = await response.json();
                const health = data.health || {};
                const harness = data.harness || {};
                const queue = (harness.queue && harness.queue.counts) || {};
                const mounts = health.services || {};

                document.getElementById('mGateway').textContent = health.status || '-';
                document.getElementById('mOrchestrator').textContent = ((health.orchestrator || {}).running ? 'running' : 'down');
                document.getElementById('mPlan').textContent = ((health.plan_council || {}).status || '-');

                document.getElementById('qPending').textContent = String(queue.pending || 0);
                document.getElementById('qProcessing').textContent = String(queue.processing || 0);
                document.getElementById('qCompleted').textContent = String(queue.completed || 0);
                document.getElementById('mountJson').textContent = JSON.stringify(mounts, null, 2);

                const quickLinks = document.getElementById('quickLinks');
                quickLinks.innerHTML = '';
                const endpoints = data.endpoints || {};
                Object.keys(endpoints).forEach(function(key) {
                    const a = document.createElement('a');
                    a.href = endpoints[key];
                    a.target = '_blank';
                    a.rel = 'noopener noreferrer';
                    a.textContent = key;
                    quickLinks.appendChild(a);
                });

                const level = health.status === 'ok' ? 'ok' : (health.status || '').toLowerCase();
                setGlobalStatus('system ' + (health.status || 'unknown'), level);
            } catch (error) {
                setGlobalStatus('system error', 'fail');
            }
        }

        async function loadPageContent() {
            const page = document.getElementById('pageSelect').value;
            if (!page) return;
            const editor = document.getElementById('contentEditor');
            editor.innerHTML = '<p>로딩 중...</p>';
            try {
                const response = await fetch('/api/contents/' + encodeURIComponent(page), {
                    headers: authHeaders()
                });
                const contents = await response.json();
                if (contents.length === 0) {
                    editor.innerHTML = '<p>아직 편집 가능한 콘텐츠가 없습니다.</p>';
                } else {
                    editor.innerHTML = contents.map(function(item) {
                        return '<div class="editable-item">' +
                            '<h3>' + escapeHtml(item.element_id) + '</h3>' +
                            '<textarea id="content-' + item.id + '" data-page="' + escapeHtml(item.page) + '" data-element="' + escapeHtml(item.element_id) + '">' + escapeHtml(item.content) + '</textarea>' +
                            '<button class="save-btn" onclick="saveContent(' + item.id + ')">저장</button>' +
                            '<span id="status-' + item.id + '" class="status"></span></div>';
                    }).join('');
                }
            } catch (error) {
                editor.innerHTML = '<p>콘텐츠를 불러오는데 실패했습니다.</p>';
            }
        }

        async function createQueueTask() {
            if (!adminToken) return;
            const agentType = document.getElementById('taskAgent').value;
            const taskType = document.getElementById('taskType').value.trim();
            const payloadRaw = document.getElementById('taskPayload').value.trim();
            const status = document.getElementById('taskStatus');

            let payload = {};
            if (!taskType) {
                status.className = 'status error';
                status.textContent = 'task_type 필요';
                return;
            }
            try {
                payload = payloadRaw ? JSON.parse(payloadRaw) : {};
            } catch (e) {
                status.className = 'status error';
                status.textContent = 'payload JSON 오류';
                return;
            }

            try {
                const response = await fetch('/queue/task', {
                    method: 'POST',
                    headers: authHeaders({'Content-Type': 'application/json'}),
                    body: JSON.stringify({
                        agent_type: agentType,
                        task_type: taskType,
                        payload: payload
                    })
                });
                if (!response.ok) {
                    throw new Error('queue task failed');
                }
                const data = await response.json();
                status.className = 'status success';
                status.textContent = '등록 완료: ' + data.task_id;
                loadSystemStatus();
            } catch (error) {
                status.className = 'status error';
                status.textContent = '등록 실패';
            }
        }

        function escapeHtml(text) {
            var div = document.createElement('div');
            div.appendChild(document.createTextNode(text));
            return div.innerHTML;
        }

        async function saveContent(id) {
            const textarea = document.getElementById('content-' + id);
            const page = textarea.dataset.page;
            const elementId = textarea.dataset.element;
            const content = textarea.value;
            const status = document.getElementById('status-' + id);
            try {
                const response = await fetch('/api/content/update', {
                    method: 'POST',
                    headers: authHeaders({'Content-Type': 'application/json'}),
                    body: JSON.stringify({ page: page, element_id: elementId, content: content })
                });
                if (response.ok) {
                    status.className = 'status success';
                    status.textContent = '저장 완료!';
                    setTimeout(function() { status.textContent = ''; }, 3000);
                } else { throw new Error('저장 실패'); }
            } catch (error) {
                status.className = 'status error';
                status.textContent = '저장 실패';
            }
        }

        function openPage() {
            const page = document.getElementById('pageSelect').value;
            if (!page) return;
            const url = page === 'index' ? '/' : '/' + page + '/';
            window.open(url, '_blank');
        }
    </script>
</body>
</html>
    """


# ─── 에러 핸들러 (디버그 정보 노출 방지) ──────────────────────

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8082)
