# apps/api/app/middleware/rate_limit.py
"""
Rate Limiting Middleware & Helpers – CursorCode AI
Production-grade global + per-route rate limiting using slowapi + Redis.
2026 standards: per-user limiting, admin bypass, audit logging on exceed.
"""

import logging
from typing import Callable, Awaitable

from fastapi import FastAPI, Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.services.logging import audit_log

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
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    return f"ip:{get_remote_address(request)}"


def get_admin_bypass_key(request: Request) -> str:
    """
    Completely bypass rate limiting for users with 'admin' role.
    Useful for debugging, monitoring tools, or admin dashboards.
    """
    user = getattr(request.state, "current_user", None)
    if user and "admin" in getattr(user, "roles", []):
        return "admin_bypass"
    return get_user_or_ip_key(request)


# ────────────────────────────────────────────────
# Custom middleware to attach limiter & user context
# ────────────────────────────────────────────────
class RateLimitMiddleware(SlowAPIMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Attach limiter to request state (for per-route use)
        request.state.limiter = limiter

        # Attach current_user.id if auth middleware ran before
        # (auth middleware should be added before rate-limit middleware)
        user = getattr(request.state, "current_user", None)
        if user and hasattr(user, "id"):
            request.state.user_id = user.id

        response = await call_next(request)
        return response


# ────────────────────────────────────────────────
# Custom exception handler for rate limit exceeded
# ────────────────────────────────────────────────
def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Handles 429 responses with Retry-After header and audit log.
    """
    user_id = getattr(request.state, "user_id", None)
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

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please try again later.",
            "retry_after": exc.retry_after if hasattr(exc, "retry_after") else 60
        },
        headers={
            "Retry-After": str(exc.retry_after) if hasattr(exc, "retry_after") else "60"
        }
    )


# ────────────────────────────────────────────────
# How to integrate in main.py
# ────────────────────────────────────────────────
"""
In apps/api/app/main.py (after creating app = FastAPI(...)):

# Attach limiter globally
app.state.limiter = limiter

# Add custom exception handler
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Add middleware (after auth middleware!)
app.add_middleware(RateLimitMiddleware)

# Example per-route limiting (uses get_user_or_ip_key by default)
@router.post("/projects")
@limiter.limit("3/minute")  # per user or IP
async def create_project(...):
    ...

# Admin bypass example
@router.get("/admin/stats")
@limiter.limit("30/minute", key_func=get_admin_bypass_key)
async def admin_stats(...):
    ...
"""

# ────────────────────────────────────────────────
# Recommended per-route limiting patterns
# ────────────────────────────────────────────────
"""
# High-security / brute-force sensitive (login, 2FA, reset)
@router.post("/auth/login")
@limiter.limit("5/minute;ip")               # strict per-IP
async def login(...): ...

# Credit-consuming / expensive actions
@router.post("/projects")
@limiter.limit("3/minute")                  # per-user (default key_func)
async def create_project(...): ...

# Admin/debug endpoints – high limit + admin bypass
@router.get("/admin/stats")
@limiter.limit("30/minute", key_func=get_admin_bypass_key)
async def admin_stats(...): ...

# Very high-traffic public endpoints (if any)
@router.get("/public/health")
@limiter.limit("500/minute;ip")
async def health(...): ...
"""
