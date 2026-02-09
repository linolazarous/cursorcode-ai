# apps/api/app/routers/admin.py
"""
Admin Router - CursorCode AI
Protected endpoints for platform administrators only.
Requires 'admin' role in JWT claims.
Statistics, user management, subscriptions, failed builds, maintenance, error logging.
"""

import logging
from datetime import datetime, timedelta
from typing import Annotated, List, Dict, Any, Optional
from zoneinfo import ZoneInfo  # Modern timezone handling

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Query,
    Body,
    Request,  # For future rate limiting or logging
)
from sqlalchemy import select, func, desc, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.middleware.auth import get_current_user, require_admin, AuthUser
from app.models.user import User
from app.models.org import Org
from app.models.project import Project, ProjectStatus
from app.services.billing import refund_credits
from app.services.logging import audit_log
from app.tasks.email import send_email_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ────────────────────────────────────────────────
# Platform Statistics Overview
# ────────────────────────────────────────────────
@router.get("/stats/overview")
async def get_platform_overview_stats(
    current_user: Annotated[AuthUser, Depends(require_admin)],
    db: AsyncSession = Depends(get_db),
    lookback_days: int = Query(30, ge=1, le=365, description="Lookback period in days")
):
    """
    High-level platform stats (users, orgs, projects, subscriptions).
    """
    since = datetime.now(ZoneInfo("UTC")) - timedelta(days=lookback_days)

    stats = {}

    # Users
    stats["users"] = {
        "total": await db.scalar(select(func.count(User.id))),
        "verified": await db.scalar(select(func.count(User.id)).where(User.is_verified == True)),
        "active_last_30d": await db.scalar(
            select(func.count(User.id)).where(User.updated_at >= since)
        ),
        "new_last_30d": await db.scalar(
            select(func.count(User.id)).where(User.created_at >= since)
        ),
    }

    # Organizations
    stats["orgs"] = {
        "total": await db.scalar(select(func.count(Org.id))),
        "active": await db.scalar(
            select(func.count(Org.id)).where(Org.deleted_at.is_(None))
        ),
    }

    # Projects
    total_projects = await db.scalar(select(func.count(Project.id)))
    stats["projects"] = {
        "total": total_projects,
        "completed": await db.scalar(select(func.count(Project.id)).where(Project.status == ProjectStatus.COMPLETED)),
        "failed": await db.scalar(select(func.count(Project.id)).where(Project.status == ProjectStatus.FAILED)),
        "building_now": await db.scalar(select(func.count(Project.id)).where(Project.status == ProjectStatus.BUILDING)),
        "failure_rate_pct": round(
            (await db.scalar(select(func.count(Project.id)).where(Project.status == ProjectStatus.FAILED))) /
            total_projects * 100 if total_projects > 0 else 0,
            1
        ),
    }

    # Subscriptions (assuming User has plan/subscription_status)
    stats["subscriptions"] = {
        "total_active": await db.scalar(
            select(func.count(User.id)).where(User.subscription_status == "active")
        ),
        "by_plan": {
            plan: await db.scalar(select(func.count(User.id)).where(User.plan == plan))
            for plan in ["starter", "standard", "pro", "premier", "ultra"]
        }
    }

    # Recent activity (24h)
    stats["recent_activity"] = {
        "new_users_24h": await db.scalar(
            select(func.count(User.id)).where(User.created_at >= datetime.now(ZoneInfo("UTC")) - timedelta(hours=24))
        ),
        "new_projects_24h": await db.scalar(
            select(func.count(Project.id)).where(Project.created_at >= datetime.now(ZoneInfo("UTC")) - timedelta(hours=24))
        ),
    }

    return stats


# ────────────────────────────────────────────────
# Recent Users (paginated + search)
# ────────────────────────────────────────────────
@router.get("/users/recent")
async def get_recent_users(
    current_user: Annotated[AuthUser, Depends(require_admin)],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=5, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Email partial match"),
):
    """
    List most recent users with pagination and optional search.
    """
    stmt = select(User).order_by(desc(User.created_at))

    if search:
        stmt = stmt.where(User.email.ilike(f"%{search}%"))

    stmt = stmt.offset(offset).limit(limit)

    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        {
            "id": str(u.id),
            "email": u.email,
            "plan": u.plan,
            "created_at": u.created_at.isoformat(),
            "is_verified": u.is_verified,
            "credits": u.credits,
            "subscription_status": u.subscription_status,
        }
        for u in users
    ]


# ────────────────────────────────────────────────
# Active Subscriptions Overview
# ────────────────────────────────────────────────
@router.get("/subscriptions/active")
async def get_active_subscriptions(
    current_user: Annotated[AuthUser, Depends(require_admin)],
    db: AsyncSession = Depends(get_db),
    plan_filter: Optional[str] = Query(None),
    status_filter: str = Query("active"),
):
    """
    List active subscriptions (filter by plan/status).
    """
    stmt = select(User).where(User.subscription_status == status_filter)

    if plan_filter:
        stmt = stmt.where(User.plan == plan_filter)

    stmt = stmt.order_by(desc(User.updated_at))

    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        {
            "user_id": str(u.id),
            "email": u.email,
            "plan": u.plan,
            "subscription_id": u.stripe_subscription_id,
            "customer_id": u.stripe_customer_id,
            "credits": u.credits,
            "updated_at": u.updated_at.isoformat(),
        }
        for u in users
    ]


# ────────────────────────────────────────────────
# Failed Projects / Builds
# ────────────────────────────────────────────────
@router.get("/projects/failed")
async def get_failed_projects(
    current_user: Annotated[AuthUser, Depends(require_admin)],
    db: AsyncSession = Depends(get_db),
    days: int = Query(7, ge=1, le=90),
):
    """
    List failed projects from the last N days.
    """
    since = datetime.now(ZoneInfo("UTC")) - timedelta(days=days)

    stmt = (
        select(Project)
        .where(Project.status == ProjectStatus.FAILED)
        .where(Project.created_at >= since)
        .order_by(desc(Project.created_at))
    )

    result = await db.execute(stmt)
    projects = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "user_id": str(p.user_id),
            "org_id": str(p.org_id),
            "title": p.title,
            "prompt_preview": p.prompt[:120] + "..." if p.prompt else "",
            "error_message": p.error_message,
            "created_at": p.created_at.isoformat(),
        }
        for p in projects
    ]


# ────────────────────────────────────────────────
# Adjust User Credits
# ────────────────────────────────────────────────
@router.post("/users/{user_id}/credits/adjust")
async def adjust_user_credits(
    user_id: str,
    amount: int = Body(..., embed=True, description="Positive = add, negative = subtract"),
    reason: str = Body(..., embed=True),
    current_user: Annotated[AuthUser, Depends(require_admin)],
    db: AsyncSession = Depends(get_db),
):
    """
    Manually adjust a user's credit balance (admin tool).
    """
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")

    old_credits = target.credits

    if amount > 0:
        target.credits += amount
    else:
        if target.credits + amount < 0:
            raise HTTPException(400, "Cannot reduce credits below zero")
        target.credits += amount

    await db.commit()
    await db.refresh(target)

    audit_log.delay(
        user_id=current_user.id,
        action="admin_credit_adjust",
        metadata={
            "target_user_id": user_id,
            "old_credits": old_credits,
            "new_credits": target.credits,
            "amount": amount,
            "reason": reason,
        }
    )

    return {
        "user_id": user_id,
        "email": target.email,
        "old_credits": old_credits,
        "new_credits": target.credits,
        "adjustment": amount,
        "reason": reason,
    }


# ────────────────────────────────────────────────
# Toggle Maintenance Mode
# ────────────────────────────────────────────────
@router.post("/maintenance")
async def toggle_maintenance_mode(
    enabled: bool = Body(..., embed=True),
    message: str = Body("Maintenance in progress – please come back later.", embed=True),
    current_user: Annotated[AuthUser, Depends(require_admin)],
):
    """
    Toggle global maintenance mode (stored in Redis or DB config).
    """
    # TODO: Implement real storage (Redis or Supabase config table)
    # Example with Redis (uncomment when Redis is ready):
    # await redis_client.set("maintenance:enabled", "1" if enabled else "0", ex=86400*7)
    # await redis_client.set("maintenance:message", message, ex=86400*7)

    audit_log.delay(
        user_id=current_user.id,
        action="maintenance_mode_toggle",
        metadata={"enabled": enabled, "message": message}
    )

    return {
        "status": "maintenance" if enabled else "normal",
        "message": message,
        "changed_by": current_user.email,
        "timestamp": datetime.now(ZoneInfo("UTC")).isoformat()
    }


# ────────────────────────────────────────────────
# Log Frontend Errors (called from Next.js)
# ────────────────────────────────────────────────
@router.post("/monitoring/frontend-error")
async def log_frontend_error(
    data: Dict[str, Any],
    current_user: Annotated[Optional[AuthUser], Depends(get_current_user)] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint for frontend to report JavaScript errors.
    Stores in Supabase 'app_errors' table.
    """
    try:
        await db.execute(
            insert("app_errors").values(
                level="frontend_error",
                message=data.get("message", "Unknown frontend error"),
                stack=data.get("stack"),
                user_id=current_user.id if current_user else None,
                request_path=data.get("url"),
                request_method="GET",  # Frontend errors usually client-side
                environment=settings.ENVIRONMENT,
                extra={
                    "user_agent": data.get("userAgent"),
                    "source": data.get("source"),
                    "timestamp": data.get("timestamp"),
                    **data,
                },
            )
        )
        await db.commit()

        logger.info(f"Frontend error logged: {data.get('message')}")
        return {"status": "logged"}
    except Exception as e:
        logger.error(f"Failed to store frontend error: {e}")
        raise HTTPException(500, "Error logging failed")
