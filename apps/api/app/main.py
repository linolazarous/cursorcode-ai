"""
CursorCode AI FastAPI Application Entry Point
Production-ready (February 2026)

Features:
- Supabase-ready external Postgres
- Proper async DB handling
- Structured logging
- Prometheus metrics
- Health / readiness / liveness probes
- Security middleware
- Rate limiting
"""

import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from sqlalchemy import text, insert

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

# Prometheus optional
try:
    from prometheus_client import generate_latest
    from app.monitoring.metrics import registry

    PROMETHEUS_ENABLED = True
except Exception:
    registry = None
    PROMETHEUS_ENABLED = False


# ────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
)

logger = logging.getLogger("cursorcode.api")


# ────────────────────────────────────────────────
# FastAPI App
# ────────────────────────────────────────────────

app = FastAPI(
    title="CursorCode AI API",
    version=settings.APP_VERSION,
    description="Autonomous AI Software Engineering Platform",
    lifespan=db_lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
    openapi_url="/openapi.json"
    if settings.ENVIRONMENT != "production"
    else None,
    debug=settings.ENVIRONMENT == "development",
)


# ────────────────────────────────────────────────
# Middleware
# ────────────────────────────────────────────────

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(o) for o in settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# Rate limit
app.add_middleware(RateLimitMiddleware)

app.state.limiter = limiter

app.add_exception_handler(
    RateLimitExceeded,
    rate_limit_exceeded_handler,
)


# ────────────────────────────────────────────────
# Routers
# ────────────────────────────────────────────────

app.include_router(auth.router, prefix="/auth")
app.include_router(orgs.router, prefix="/orgs")
app.include_router(projects.router, prefix="/projects")
app.include_router(billing.router, prefix="/billing")
app.include_router(webhook.router, prefix="/webhook")
app.include_router(admin.router, prefix="/admin")
app.include_router(monitoring.router, prefix="/monitoring")


# ────────────────────────────────────────────────
# Root
# ────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():

    if settings.ENVIRONMENT != "production":

        return RedirectResponse("/docs")

    return {"status": "ok"}


# ────────────────────────────────────────────────
# Prometheus
# ────────────────────────────────────────────────

@app.get("/metrics", include_in_schema=False)
async def metrics():

    if not PROMETHEUS_ENABLED:

        return {"detail": "Prometheus disabled"}

    return Response(
        generate_latest(registry),
        media_type="text/plain",
    )


# ────────────────────────────────────────────────
# Exception Handler
# ────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception,
):

    logger.exception("Unhandled error")

    try:

        db_gen = get_db()

        db = await db_gen.__anext__()

        await db.execute(
            insert(text("app_errors")).values(
                level="error",
                message=str(exc),
                stack=traceback.format_exc(),
                request_path=request.url.path,
                request_method=request.method,
                environment=settings.ENVIRONMENT,
            )
        )

        await db.commit()

    except Exception as db_exc:

        logger.error(f"Error logging failed: {db_exc}")

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ────────────────────────────────────────────────
# Health
# ────────────────────────────────────────────────

@app.get("/health")
async def health():

    return {

        "status": "healthy",

        "version": settings.APP_VERSION,

    }


# ────────────────────────────────────────────────
# Readiness
# ────────────────────────────────────────────────

@app.get("/ready")
async def ready():

    try:

        db_gen = get_db()

        db = await db_gen.__anext__()

        await db.execute(text("SELECT 1"))

        return {"status": "ready"}

    except Exception as e:

        logger.error("Readiness failed", exc_info=True)

        return JSONResponse(

            status_code=503,

            content={

                "status": "not ready",

                "error": str(e),

            },

        )


# ────────────────────────────────────────────────
# Liveness
# ────────────────────────────────────────────────

@app.get("/live")
async def live():

    return {"status": "alive"}
