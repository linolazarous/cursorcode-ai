"""
Monitoring Router - CursorCode AI
Endpoints for logging and observability.
Frontend error reporting, health checks.
"""

import logging
from typing import Dict, Any, Optional

from fastapi import (
    APIRouter,
    Request,
    Body,
    HTTPException,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter

from app.core.config import settings
from app.core.deps import DBSession, OptionalCurrentUser, get_user_id_or_ip
from app.services.logging import audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])

# Rate limiter: prefer user ID if authenticated, fallback to IP
limiter = Limiter(key_func=get_user_id_or_ip)


# ────────────────────────────────────────────────
# Payload validation
# ────────────────────────────────────────────────
class FrontendErrorPayload(BaseModel):
    message: str = Field(..., min_length=1, description="Error message")
    stack: Optional[str] = Field(None, description="Stack trace")
    url: Optional[str] = Field(None, description="Page URL")
    component: Optional[str] = Field(None, description="Component name")
    userAgent: Optional[str] = Field(None, description="Browser user agent")
    source: Optional[str] = Field(None, description="Error source file/line")
    timestamp: Optional[str] = Field(None, description="Client timestamp")


# ────────────────────────────────────────────────
# Log Frontend Error (called from Next.js)
# ────────────────────────────────────────────────
@router.post("/log-error", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def log_frontend_error(
    request: Request,
    payload: FrontendErrorPayload = Body(...),
    current_user: OptionalCurrentUser = None,
    db: DBSession,
):
    """
    Receives frontend JS/runtime errors from Next.js.
    Stores in Supabase 'app_errors' table.
    Returns 200 even on failure (frontend should not retry).
    """
    message = payload.message
    url = payload.url
    component = payload.component
    stack = payload.stack
    user_agent = payload.userAgent
    source = payload.source

    user_id = current_user.id if current_user else None
    ip = request.client.host

    # Structured logging
    logger.error(
        "Frontend error received",
        extra={
            "message": message,
            "url": url,
            "component": component,
            "stack": stack[:1000] if stack else None,
            "user_agent": user_agent,
            "source": source,
            "user_id": user_id,
            "ip": ip,
            "environment": settings.ENVIRONMENT,
            "request_path": str(request.url),
            "request_method": request.method,
        }
    )

    # Store in DB
    try:
        await db.execute(
            insert("app_errors").values(
                level="frontend_error",
                message=message,
                stack=stack,
                user_id=user_id,
                request_path=url or str(request.url),
                request_method="CLIENT_SIDE",
                environment=settings.ENVIRONMENT,
                extra={
                    "component": component,
                    "user_agent": user_agent,
                    "source": source,
                    "ip": ip,
                    "payload": payload.dict(exclude_unset=True),
                    "timestamp": datetime.now(ZoneInfo("UTC")).isoformat(),
                },
            )
        )
        await db.commit()
    except Exception as db_exc:
        logger.error(f"Failed to store frontend error in DB: {db_exc}")

    # Audit log
    audit_log.delay(
        user_id=user_id,
        action="frontend_error_logged",
        metadata={
            "message": message[:200],
            "url": url,
            "component": component,
            "user_agent": user_agent,
            "ip": ip,
            "stack_length": len(stack) if stack else 0,
        },
        request=request,
    )

    return {"status": "logged"}


# ────────────────────────────────────────────────
# Health check (public)
# ────────────────────────────────────────────────
@router.get("/health")
async def monitoring_health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(ZoneInfo("UTC")).isoformat(),
        "service": "monitoring-router",
    }
