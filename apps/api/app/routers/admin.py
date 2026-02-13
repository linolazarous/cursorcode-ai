"""
Admin Router - CursorCode AI
Protected endpoints for platform administrators only.
Requires 'admin' role in JWT claims.
Statistics, user management, subscriptions, failed builds, maintenance, error logging.
"""

import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional, Dict, Any
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Query,
    Body,
    Request,
)
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import DBSession, CurrentAdminUser, OptionalCurrentUser  # ← use centralized deps
from app.db.models.user import User
from app.db.models.org import Org
from app.db.models.project import Project, ProjectStatus
from app.services.billing import refund_credits
from app.services.logging import audit_log
from app.tasks.email import send_email_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ────────────────────────────────────────────────
# Models
# ────────────────────────────────────────────────
class MaintenanceToggle(BaseModel):
    enabled: bool = Field(...)
    message: str = Field(default="Maintenance in progress – please come back later.")


class CreditAdjust(BaseModel):
    amount: int = Field(..., description="Positive = add, negative = subtract")
    reason: str = Field(..., min_length=5)


class AdminStatsOverview(BaseModel):
    users: Dict[str, int]
    orgs: Dict[str, int]
    projects: Dict[str, Any]
    subscriptions: Dict[str, Any]
    recent_activity: Dict[str, int]


# ────────────────────────────────────────────────
# Platform Statistics Overview
# ────────────────────────────────────────────────
@router.get("/stats/overview", response_model=AdminStatsOverview)
async def get_platform_overview_stats(
    current_user: CurrentAdminUser,
    db: DBSession,
    lookback_days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
):
    """
    High-level platform stats (users, orgs, projects, subscriptions).
    """
    since = datetime.now(ZoneInfo("UTC")) - timedelta(days=lookback_days)

    stats = {}

    # Users
    total_users = await db.scalar(select(func.count(User.id)))
    stats["users"] = {
        "total": total_users,
        "verified": await db.scalar(select(func.count(User.id)).where(User.is_verified == True)),
        "active_last_30d": await db.scalar(select(func.count(User.id)).where(User.updated_at >= since)),
        "new_last_30d": await db.scalar(select(func.count(User.id)).where(User.created_at >= since)),
    }

    # Organizations
    stats["orgs"] = {
        "total": await db.scalar(select(func.count(Org.id))),
        "active": await db.scalar(select(func.count(Org.id)).where(Org.deleted_at.is_(None))),
    }

    # Projects
    total_projects = await db.scalar(select(func.count(Project.id)))
    failed_projects = await db.scalar(select(func.count(Project.id)).where(Project.status == ProjectStatus.FAILED))
    stats["projects"] = {
        "total": total_projects,
        "completed": await db.scalar(select(func.count(Project.id)).where(Project.status == ProjectStatus.COMPLETED)),
        "failed": failed_projects,
        "building_now": await db.scalar(select(func.count(Project.id)).where(Project.status == ProjectStatus.BUILDING)),
        "failure_rate_pct": round(failed_projects / total_projects * 100, 1) if total_projects > 0 else 0.0,
    }

    # Subscriptions
    stats["subscriptions"] = {
        "total_active": await db.scalar(select(func.count(User.id)).where(User.subscription_status == "active")),
        "by_plan": {
            plan: await db.scalar(select(func.count(User.id)).where(User.plan == plan))
            for plan in ["starter", "standard", "pro", "premier", "ultra"]
        }
    }

    # Recent activity (24h)
    since_24h = datetime.now(ZoneInfo("UTC")) - timedelta(hours=24)
    stats["recent_activity"] = {
        "new_users_24h": await db.scalar(select(func.count(User.id)).where(User.created_at >= since_24h)),
        "new_projects_24h": await db.scalar(select(func.count(Project.id)).where(Project.created_at >= since_24h)),
    }

    return stats


# ────────────────────────────────────────────────
# Recent Users (paginated + search)
# ────────────────────────────────────────────────
@router.get("/users/recent")
async def get_recent_users(
    current_user: CurrentAdminUser,
    db: DBSession,
    limit: int = Query(20, ge=5, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Email or name partial match"),
):
    """
    List most recent users with pagination and optional search.
    """
    stmt = select(User).order_by(desc(User.created_at))

    if search:
        search = f"%{search}%"
        stmt = stmt.where((User.email.ilike(search)) | (User.name.ilike(search)))

    stmt = stmt.offset(offset).limit(limit)

    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
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
    current_user: CurrentAdminUser,
    db: DBSession,
    plan_filter: Optional[str] = Query(None, description="Filter by plan type"),
    status_filter: str = Query("active", description="Subscription status filter"),
    limit: int = Query(20, ge=5, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List active subscriptions (paginated, filterable).
    """
    stmt = select(User).where(User.subscription_status == status_filter)

    if plan_filter:
        stmt = stmt.where(User.plan == plan_filter)

    stmt = stmt.order_by(desc(User.updated_at)).offset(offset).limit(limit)

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
    current_user: CurrentAdminUser,
    db: DBSession,
    days: int = Query(7, ge=1, le=90, description="Lookback days"),
    limit: int = Query(20, ge=5, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List failed projects from the last N days (paginated).
    """
    since = datetime.now(ZoneInfo("UTC")) - timedelta(days=days)

    stmt = (
        select(Project)
        .where(Project.status == ProjectStatus.FAILED)
        .where(Project.created_at >= since)
        .order_by(desc(Project.created_at))
        .offset(offset)
        .limit(limit)
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
    payload: CreditAdjust = Body(...),
    current_user: CurrentAdminUser,
    db: DBSession,
):
    """
    Manually adjust a user's credit balance (admin tool).
    """
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    old_credits = target.credits
    new_credits = old_credits + payload.amount

    if new_credits < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot reduce credits below zero")

    target.credits = new_credits
    await db.commit()
    await db.refresh(target)

    audit_log.delay(
        user_id=current_user.id,
        action="admin_credit_adjust",
        metadata={
            "target_user_id": user_id,
            "old_credits": old_credits,
            "new_credits": new_credits,
            "amount": payload.amount,
            "reason": payload.reason,
        }
    )

    return {
        "user_id": user_id,
        "email": target.email,
        "old_credits": old_credits,
        "new_credits": new_credits,
        "adjustment": payload.amount,
        "reason": payload.reason,
    }


# ────────────────────────────────────────────────
# Toggle Maintenance Mode
# ────────────────────────────────────────────────
@router.post("/maintenance")
async def toggle_maintenance_mode(
    payload: MaintenanceToggle = Body(...),
    current_user: CurrentAdminUser,
):
    """
    Toggle global maintenance mode.
    (Currently in-memory; implement Redis/DB storage in production)
    """
    # TODO: Store in Redis or Supabase config table
    # Example Redis:
    # async with get_redis_client() as redis:
    #     await redis.set("maintenance:enabled", "1" if payload.enabled else "0", ex=86400*7)
    #     await redis.set("maintenance:message", payload.message, ex=86400*7)

    audit_log.delay(
        user_id=current_user.id,
        action="maintenance_mode_toggle",
        metadata={"enabled": payload.enabled, "message": payload.message}
    )

    return {
        "status": "maintenance" if payload.enabled else "normal",
        "message": payload.message,
        "changed_by": current_user.email,
        "timestamp": datetime.now(ZoneInfo("UTC")).isoformat()
    }


# ────────────────────────────────────────────────
# Log Frontend Errors (called from Next.js)
# ────────────────────────────────────────────────
@router.post("/monitoring/frontend-error")
async def log_frontend_error(
    request: Request,  # ← added for IP logging
    data: Dict[str, Any] = Body(...),
    current_user: OptionalCurrentUser = None,  # optional
    db: DBSession,
):
    """
    Endpoint for frontend to report JavaScript/runtime errors.
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
                request_method="GET",
                environment=settings.ENVIRONMENT,
                extra={
                    "user_agent": data.get("userAgent"),
                    "source": data.get("source"),
                    "timestamp": data.get("timestamp"),
                    "ip": request.client.host,
                    **data,
                },
            )
        )
        await db.commit()

        logger.info(f"Frontend error logged: {data.get('message')}")
        return {"status": "logged"}

    except Exception as e:
        logger.error(f"Failed to store frontend error: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error logging failed")
