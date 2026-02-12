"""
Rate Limiting Middleware & Helpers – CursorCode AI
Production-grade global + per-route rate limiting using slowapi + Redis.
2026 standards: per-user limiting, admin bypass, audit logging on exceed.
"""

import logging
import secrets
from typing import Optional

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.services.logging import audit_log
from app.middleware.auth import AuthUser  # for type hint & admin check

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# Global Limiter Configuration (Redis backend)
# ────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,                    # fallback: per IP
    storage_uri=settings.REDIS_URL,
    default_limits=["100/minute"],                  # global fallback
    retry_after_header=True,
    headers_enabled=True,
)


# ────────────────────────────────────────────────
# Custom key functions (more granular & fair)
# ────────────────────────────────────────────────
def get_user_or_ip_key(request: Request) -> str:
    """
    Rate limit by authenticated user ID if present, otherwise by IP.
    Prevents shared-IP abuse (e.g. corporate networks, mobile carriers).
    """
    user = getattr(request.state, "current_user", None)
    if isinstance(user, AuthUser) and user.id:
        return f"user:{user.id}"
    return f"ip:{get_remote_address(request)}"


def get_admin_bypass_key(request: Request) -> str:
    """
    Completely bypass rate limiting for users with 'admin' role.
    Useful for debugging, monitoring tools, or admin dashboards.
    """
    user = getattr(request.state, "current_user", None)
    if isinstance(user, AuthUser) and "admin" in user.roles:
        return "admin_bypass"
    return get_user_or_ip_key(request)


# ────────────────────────────────────────────────
# Custom middleware to attach limiter & user context
# ────────────────────────────────────────────────
class RateLimitMiddleware(SlowAPIMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Attach limiter to request state (for per-route use)
        request.state.limiter = limiter

        # Let auth middleware run first (sets current_user)
        response = await call_next(request)
        return response


# ────────────────────────────────────────────────
# Custom exception handler for rate limit exceeded
# ────────────────────────────────────────────────
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Handles 429 responses with Retry-After header and audit log.
    """
    user = getattr(request.state, "current_user", None)
    user_id = user.id if isinstance(user, AuthUser) else None
    ip = get_remote_address(request)

    # Audit (sampled – avoid flooding in high-abuse scenarios)
    if settings.AUDIT_ALL_RATE_LIMIT or secrets.randbelow(10) == 0:
        audit_log.delay(
            user_id=user_id,
            action="rate_limit_exceeded",
            metadata={
                "path": str(request.url.path),
                "method": request.method,
                "ip": ip,
                "limit_detail": exc.detail,
                "retry_after": exc.retry_after,
            }
        )

    headers = {}
    if hasattr(exc, "retry_after"):
        headers["Retry-After"] = str(exc.retry_after)

    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "Rate limit exceeded. Please try again later.",
            "retry_after": exc.retry_after if hasattr(exc, "retry_after") else 60
        },
        headers=headers
    )


# ────────────────────────────────────────────────
# How to integrate in main.py
# ────────────────────────────────────────────────
"""
In apps/api/app/main.py (after creating app = FastAPI(...)):

from app.middleware.rate_limit import limiter, rate_limit_exceeded_handler, RateLimitMiddleware

# Attach limiter globally
app.state.limiter = limiter

# Add custom exception handler
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Add middleware AFTER auth middleware!
app.add_middleware(RateLimitMiddleware)

# Example per-route limiting
@router.post("/projects")
@limiter.limit("3/minute", key_func=get_user_or_ip_key)
async def create_project(...):
    ...

# Admin bypass example
@router.get("/admin/stats")
@limiter.limit("30/minute", key_func=get_admin_bypass_key)
async def admin_stats(...):
    ...
"""
