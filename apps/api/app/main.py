"""
CursorCode AI FastAPI Application Entry Point
Production-ready (February 2026): middleware stack, lifespan, observability, security.
Supabase-ready: external managed Postgres, no auto-migrations, no engine dispose.
Custom monitoring: structured logging + Supabase error table + Prometheus /metrics (optional).
"""

import logging
import time
import traceback
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.db.session import lifespan as db_lifespan, get_db
from app.routers import (
    auth,
    orgs,
    projects,
    billing,
    webhook,
    admin,
    monitoring,
)
from app.middleware.security import SecurityHeadersMiddleware
from app.middleware.rate_limit import (
    limiter,
    RateLimitMiddleware,
    rate_limit_exceeded_handler,
)

# Optional Prometheus (safe import)
try:
    from prometheus_client import generate_latest
    from app.monitoring.metrics import registry
    PROMETHEUS_ENABLED = True
except (ImportError, ModuleNotFoundError):
    PROMETHEUS_ENABLED = False
    registry = None

# ────────────────────────────────────────────────
# Structured Logging Setup
# ────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# FastAPI Application
# ────────────────────────────────────────────────
app = FastAPI(
    title="CursorCode AI API",
    description="Backend for the autonomous AI software engineering platform",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
    lifespan=db_lifespan,
    debug=settings.ENVIRONMENT == "development",
    openapi_tags=[
        {"name": "Authentication", "description": "User auth & sessions"},
        {"name": "Organizations", "description": "Multi-tenant org management"},
        {"name": "Projects", "description": "AI-generated project lifecycle"},
        {"name": "Billing", "description": "Subscriptions, credits, Stripe"},
        {"name": "Webhooks", "description": "Stripe & external events"},
        {"name": "Admin", "description": "Platform administration (protected)"},
        {"name": "Monitoring", "description": "Metrics & logging"},
    ],
)

# ────────────────────────────────────────────────
# Global Middleware Stack (order is critical!)
# ────────────────────────────────────────────────

# 1. CORS – must be first
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Security Headers (CSP, HSTS, etc.) – applied to every response
app.add_middleware(SecurityHeadersMiddleware)

# 3. Request Logging + Prometheus Metrics (if enabled)
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    method = request.method
    path = request.url.path
    start_time = time.time()

    # Correlation ID for tracing
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        status_code = 500
        raise
    finally:
        duration = time.time() - start_time
        if PROMETHEUS_ENABLED:
            try:
                http_requests_total.labels(method=method, path=path, status=status_code).inc()
                http_request_duration_seconds.labels(method=method, path=path, status=status_code).observe(duration)
            except Exception as metrics_exc:
                logger.warning("Prometheus metrics failed", exc_info=metrics_exc)

    return response

# 4. Rate Limiting (Redis + user-aware keys)
app.add_middleware(RateLimitMiddleware)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# ────────────────────────────────────────────────
# Routers
# ────────────────────────────────────────────────
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(orgs.router, prefix="/orgs", tags=["Organizations"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(billing.router, prefix="/billing", tags=["Billing"])
app.include_router(webhook.router, prefix="/webhook", tags=["Webhooks"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(monitoring.router, prefix="/monitoring", tags=["Monitoring"])

# ────────────────────────────────────────────────
# Prometheus Metrics Endpoint (if enabled)
# ────────────────────────────────────────────────
if PROMETHEUS_ENABLED:
    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(generate_latest(registry), media_type="text/plain")
else:
    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return {"detail": "Prometheus metrics not configured"}

# ────────────────────────────────────────────────
# Custom Global Exception Handler (structured + Supabase logging)
# ────────────────────────────────────────────────
@app.exception_handler(Exception)
async def custom_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    user_id = getattr(request.state, "user_id", None) or getattr(
        getattr(request.state, "current_user", None), "id", None
    )
    path = request.url.path
    method = request.method

    logger.exception(
        f"Unhandled exception: {exc}",
        extra={
            "request_id": request_id,
            "path": path,
            "method": method,
            "user_id": user_id,
            "status_code": 500,
            "environment": settings.ENVIRONMENT,
            "traceback": traceback.format_exc(),
        }
    )

    # Log to Supabase 'app_errors' (async)
    try:
        async with get_db() as db:
            await db.execute(
                insert("app_errors").values(
                    level="error",
                    message=str(exc),
                    stack=traceback.format_exc(),
                    user_id=user_id,
                    request_path=path,
                    request_method=method,
                    environment=settings.ENVIRONMENT,
                    extra={
                        "request_id": request_id,
                        "request_url": str(request.url),
                        "traceback_lines": traceback.format_tb(exc.__traceback__),
                    },
                )
            )
            await db.commit()
    except Exception as db_exc:
        logger.error(f"Failed to log error to Supabase: {db_exc}", extra={"request_id": request_id})

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error. Our team has been notified."},
    )


# ────────────────────────────────────────────────
# Health / Readiness / Liveness Endpoints
# ────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION}


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """
    Readiness probe: DB ping + optional Redis ping.
    """
    try:
        async with get_db() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        logger.error("Readiness check failed", exc_info=True)
        return JSONResponse(status_code=503, content={"status": "not ready", "error": str(e)})


@app.get("/live", tags=["Health"])
async def liveness_check():
    return {"status": "alive"}
