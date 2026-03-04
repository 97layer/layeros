"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import auth_router, products_router, cart_router, orders_router, payments_router
from .config import settings
from .models import init_db
from .utils import normalize_tenant_id
from core.system.security import load_cors_origins


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize resources on startup."""
    init_db()
    yield


# Create FastAPI app
app = FastAPI(
    title="WOOHWAHAE E-commerce API",
    description="Product catalog, cart, and order management API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=load_cors_origins(default=settings.CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Session-ID", settings.TENANT_HEADER],
)


@app.middleware("http")
async def tenant_context_middleware(request: Request, call_next):
    """Attach tenant context for every request and echo resolved tenant header."""
    raw_tenant_id = request.headers.get(settings.TENANT_HEADER)
    if settings.REQUIRE_TENANT_HEADER and not raw_tenant_id:
        return JSONResponse(
            status_code=400,
            content={"detail": f"{settings.TENANT_HEADER} header required"},
        )
    candidate = raw_tenant_id or settings.DEFAULT_TENANT_ID
    try:
        tenant_id = normalize_tenant_id(candidate)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    request.state.tenant_id = tenant_id
    response = await call_next(request)
    response.headers[settings.TENANT_HEADER] = tenant_id
    return response

# Register routers
API_V1_PREFIX = "/api/v1"

app.include_router(auth_router, prefix=API_V1_PREFIX)
app.include_router(products_router, prefix=API_V1_PREFIX)
app.include_router(cart_router, prefix=API_V1_PREFIX)
app.include_router(orders_router, prefix=API_V1_PREFIX)
app.include_router(payments_router, prefix=API_V1_PREFIX)


@app.get("/")
def root():
    """API root endpoint."""
    return {
        "message": "WOOHWAHAE E-commerce API",
        "version": "1.0.0",
        "docs": "/api/docs"
    }


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
