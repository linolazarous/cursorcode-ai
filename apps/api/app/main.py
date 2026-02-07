# apps/api/app/main.py
"""
CursorCode AI FastAPI Application Entry Point
Production-ready (February 2026): middleware, lifespan, observability, routers, security.
Supabase-ready: external managed Postgres, no auto-migrations on startup.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import sentry_sdk
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.db.session import engine, init_db   # init_db now only tests connection
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
from app.middleware.rate_limit import limiter, rate_limit_exceeded_handler, RateLimitMiddleware

# ────────────────────────────────────────────────
# Sentry (observability & error tracking)
# ────────────────────────────────────────────────
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=1.0 if settings.ENVIRONMENT != "production" else 0.2,
        profiles_sample_rate=0.5 if settings.ENVIRONMENT != "production" else 0.2,
        environment=settings.ENVIRONMENT,
        release=f"cursorcode-api@{settings.APP_VERSION}",
        attach_stacktrace=True,
        send_default_pii=False,           # GDPR compliance
        max_breadcrumbs=50,
        before_send=lambda event, hint: event if not event.get("user") else None,
    )

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
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

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
        # Only test connection (no auto-migrations — use Supabase dashboard or CLI)
        await init_db()
        logger.info("Supabase PostgreSQL connection verified")
    except Exception as exc:
        logger.critical(f"Supabase connection failed on startup: {exc}")
        sentry_sdk.capture_exception(exc)
        # In production: continue with alert (don't crash) unless critical
        # raise exc  # uncomment only if you want hard fail on DB down

    # Optional: warm Redis cache, check Stripe/SendGrid connectivity, etc.
    # await redis_client.ping()

    yield

    # ── Shutdown ────────────────────────────────────
    logger.info("CursorCode AI API shutting down...")
    # Supabase pooling is external — no need to dispose engine aggressively
    # await engine.dispose()  # optional; can cause warnings in some hosts
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

# 3. Structured Request Logging
app.add_middleware(BaseHTTPMiddleware, dispatch=log_requests_middleware)

# 4. Rate Limiting Middleware (Redis + user-aware keys)
app.add_middleware(RateLimitMiddleware)

# Custom auth middleware — applied selectively via Depends (not global)
# Do NOT add app.middleware('http')(auth_middleware) here

# ────────────────────────────────────────────────
# Routers (all prefixed & tagged for OpenAPI)
# ────────────────────────────────────────────────
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(orgs.router, prefix="/orgs", tags=["Organizations"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(billing.router, prefix="/billing", tags=["Billing"])
app.include_router(webhook.router, prefix="/webhook", tags=["Webhooks"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])

# ────────────────────────────────────────────────
# Global Exception Handler
# ────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    sentry_sdk.capture_exception(exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error. Our team has been notified."},
    )


# ────────────────────────────────────────────────
# Health / Readiness / Liveness (K8s / Render / Railway friendly)
# ────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION}


@app.get("/ready", tags=["Health"])
async def readiness_check():
    # In real prod: ping Supabase, Redis, Stripe connectivity if critical
    return {"status": "ready"}


@app.get("/live", tags=["Health"])
async def liveness_check():
    return {"status": "alive"}


# ────────────────────────────────────────────────
# Startup Event (extra logging & optional notification)
# ────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    db_host = "Supabase" if "supabase" in str(settings.DATABASE_URL).lower() else \
              (settings.DATABASE_URL.host if hasattr(settings.DATABASE_URL, 'host') else 'unknown')

    redis_host = settings.REDIS_URL.host if hasattr(settings.REDIS_URL, 'host') else 'unknown'

    logger.info(
        f"CursorCode AI API v{settings.APP_VERSION} "
        f"started successfully in {settings.ENVIRONMENT.upper()} mode "
        f"(DB: {db_host}, Redis: {redis_host})"
    )

    # Optional: notify admin/Slack on production startup
    if settings.ENVIRONMENT == "production":
        # send_email_task.delay(
        #     to="admin@cursorcode.ai",
        #     subject="API Started (Production)",
        #     template_id="d-api-startup",
        #     dynamic_data={"version": settings.APP_VERSION, "env": settings.ENVIRONMENT}
        # )
        pass
