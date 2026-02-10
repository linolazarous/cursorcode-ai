# apps/api/app/main.py
"""
CursorCode AI FastAPI Application Entry Point
Production-ready (February 2026): middleware, lifespan, observability, security.
Supabase-ready: external managed Postgres, no auto-migrations, no engine dispose.
Custom monitoring: structured logging + Supabase error table + Prometheus /metrics.
"""

import logging
import time
import traceback
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import insert
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.db.session import engine, init_db
from app.routers import (
    auth,
    orgs,
    projects,
    billing,
    webhook,
    admin,
)
from app.middleware.auth import auth_middleware           # Selective (Depends)
from app.middleware.logging import log_requests_middleware
from app.middleware.security import add_security_headers
from app.middleware.rate_limit import limiter, RateLimitMiddleware

# Prometheus metrics (custom monitoring)
from app.monitoring.metrics import registry, http_requests_total, http_request_duration_seconds
from prometheus_client import generate_latest

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
# Global Rate Limiter (Redis-backed)
# ────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ────────────────────────────────────────────────
# Lifespan (startup & shutdown) – Supabase-friendly
# ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ─────────────────────────────────────
    logger.info(
        f"Starting CursorCode AI API v{settings.APP_VERSION} "
        f"in {settings.ENVIRONMENT.upper()} mode"
    )

    try:
        await init_db()
        db_type = "Supabase" if "supabase" in str(settings.DATABASE_URL).lower() else "PostgreSQL"
        logger.info(f"{db_type} connection verified")
    except Exception as exc:
        logger.critical(f"Database connection failed on startup: {exc}")
        # Continue in production (alert via logs/Prometheus)

    yield

    # ── Shutdown ────────────────────────────────────
    logger.info("CursorCode AI API shutting down...")
    logger.info("Shutdown complete")


# ────────────────────────────────────────────────
# FastAPI Application
# ────────────────────────────────────────────────
app = FastAPI(
    title="CursorCode AI API",
    description="Backend for the autonomous AI software engineering platform",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
    debug=settings.ENVIRONMENT == "development",
    openapi_tags=[
        {"name": "Authentication", "description": "User auth & sessions"},
        {"name": "Organizations", "description": "Multi-tenant org management"},
        {"name": "Projects", "description": "AI-generated project lifecycle"},
        {"name": "Billing", "description": "Subscriptions, credits, Stripe"},
        {"name": "Webhooks", "description": "Stripe & external events"},
        {"name": "Admin", "description": "Platform administration (protected)"},
        {"name": "Health", "description": "Health & readiness checks"},
        {"name": "Monitoring", "description": "Metrics & logging"},
    ],
)

# ────────────────────────────────────────────────
# Global Middleware Stack (order matters!)
# ────────────────────────────────────────────────
# 1. CORS (must be first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Security Headers (CSP, HSTS, etc.)
app.add_middleware(BaseHTTPMiddleware, dispatch=add_security_headers)

# 3. Structured Request Logging + Prometheus instrumentation
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    method = request.method
    path = request.url.path
    start_time = time.time()

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        status_code = 500
        raise
    finally:
        duration = time.time() - start_time
        http_requests_total.labels(method=method, path=path, status=status_code).inc()
        http_request_duration_seconds.labels(method=method, path=path).observe(duration)

    return response

# 4. Rate Limiting Middleware (Redis + user-aware keys)
app.add_middleware(RateLimitMiddleware)

# Custom auth middleware — applied selectively via Depends (not global)
# Do NOT add app.middleware('http')(auth_middleware) here

# ────────────────────────────────────────────────
# Routers
# ────────────────────────────────────────────────
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(orgs.router, prefix="/orgs", tags=["Organizations"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(billing.router, prefix="/billing", tags=["Billing"])
app.include_router(webhook.router, prefix="/webhook", tags=["Webhooks"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])

# ────────────────────────────────────────────────
# Prometheus Metrics Endpoint
# ────────────────────────────────────────────────
@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(registry), media_type="text/plain")


# ────────────────────────────────────────────────
# Custom Global Exception Handler (custom monitoring)
# ────────────────────────────────────────────────
@app.exception_handler(Exception)
async def custom_exception_handler(request: Request, exc: Exception):
    """
    Custom monitoring handler:
    - Structured logging with context
    - Store error in Supabase 'app_errors' table
    - Return user-friendly 500 response
    """
    user_id = getattr(request.state, "user_id", None)
    path = request.url.path
    method = request.method

    # Structured log
    logger.exception(
        f"Unhandled exception: {exc}",
        extra={
            "path": path,
            "method": method,
            "user_id": user_id,
            "status_code": 500,
            "environment": settings.ENVIRONMENT,
            "traceback": traceback.format_exc(),
        }
    )

    # Log to Supabase (async)
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
                        "request_url": str(request.url),
                    },
                )
            )
            await db.commit()
    except Exception as db_exc:
        logger.error(f"Failed to log error to Supabase: {db_exc}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error. Our team has been notified."},
    )


# ────────────────────────────────────────────────
# Health / Readiness / Liveness
# ────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION}


@app.get("/ready", tags=["Health"])
async def readiness_check():
    # Optional: add real checks (DB ping, Redis ping)
    return {"status": "ready"}


@app.get("/live", tags=["Health"])
async def liveness_check():
    return {"status": "alive"}


# ────────────────────────────────────────────────
# Startup Logging (moved from deprecated @app.on_event)
# ────────────────────────────────────────────────
@app.on_startup
async def startup_event():
    db_host = "Supabase" if "supabase" in str(settings.DATABASE_URL).lower() else \
              (settings.DATABASE_URL.host if hasattr(settings.DATABASE_URL, 'host') else 'unknown')

    redis_host = settings.REDIS_URL.host if hasattr(settings.REDIS_URL, 'host') else 'unknown'

    logger.info(
        f"CursorCode AI API v{settings.APP_VERSION} "
        f"started successfully in {settings.ENVIRONMENT.upper()} mode "
        f"(DB: {db_host}, Redis: {redis_host})"
    )
