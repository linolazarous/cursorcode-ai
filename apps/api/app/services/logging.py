# apps/api/app/services/logging.py
"""
Audit Logging Service - CursorCode AI
Immutable, async, retryable audit trail for compliance & security.
Logs all significant user actions (login, signup, 2FA, billing, project creation, etc.).
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from celery import shared_task
from fastapi import Request
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


@shared_task(
    name="app.tasks.logging.audit_log",
    bind=True,
    max_retries=5,
    default_retry_delay=30,       # seconds
    retry_backoff=True,
    retry_jitter=True,
    acks_late=True,
)
async def audit_log_task(
    self,
    user_id: Optional[str] = None,
    action: str,
    metadata: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[str] = None,
    event_id: Optional[str] = None,  # for deduplication / tracing
):
    """
    Celery async task: Create immutable audit log entry.
    Retries on DB failure, ensures delivery.
    """
    if event_id is None:
        event_id = str(uuid.uuid4())

    try:
        async with async_session_factory() as db:
            stmt = insert(AuditLog).values(
                event_id=event_id,
                user_id=user_id,
                action=action,
                event_metadata=metadata or {},
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                created_at=datetime.now(timezone.utc),
            )
            await db.execute(stmt)
            await db.commit()

        logger.info(
            f"AUDIT [{event_id}]: {action}",
            extra={
                "user_id": user_id,
                "metadata": json.dumps(metadata or {}, default=str),
                "ip": ip_address,
                "user_agent": user_agent,
                "request_id": request_id,
            }
        )

    except Exception as exc:
        logger.exception(
            f"Audit log failed for action '{action}' (event_id={event_id})",
            extra={"exc_info": str(exc)}
        )
        raise self.retry(exc=exc)


# ────────────────────────────────────────────────
# Public sync wrapper (queues Celery task)
# ────────────────────────────────────────────────
def audit_log(
    user_id: Optional[str] = None,
    action: str,
    metadata: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
    event_id: Optional[str] = None,
):
    """
    Convenience sync caller: queues the Celery audit task.
    Use in middleware, routes, or services.

    Args:
        user_id: Authenticated user ID (str)
        action: Descriptive action name (e.g. "login_success", "project_created")
        metadata: Optional dict of context (will be JSON-serialized)
        request: FastAPI Request (for IP, user-agent, request ID)
        event_id: Optional external trace ID (for correlation)
    """
    ip = request.client.host if request else None
    ua = request.headers.get("user-agent") if request else None
    req_id = request.headers.get("X-Request-ID") if request else None

    audit_log_task.delay(
        user_id=user_id,
        action=action,
        metadata=metadata,
        ip_address=ip,
        user_agent=ua,
        request_id=req_id,
        event_id=event_id,
    )


# ────────────────────────────────────────────────
# Example usage patterns
# ────────────────────────────────────────────────
"""
# In login endpoint (auth.py):
audit_log(
    user_id=user.id,
    action="login_success",
    metadata={"method": "password+2fa", "ip": request.client.host},
    request=request
)

# In project creation (projects.py):
audit_log(
    user_id=current_user.id,
    action="project_created",
    metadata={
        "project_id": str(project.id),
        "title": project.title,
        "prompt_length": len(payload.prompt),
    },
    request=request
)

# In middleware (after auth):
audit_log(
    user_id=user.id,
    action="api_access",
    metadata={"path": request.url.path, "method": request.method},
    request=request
)
"""
