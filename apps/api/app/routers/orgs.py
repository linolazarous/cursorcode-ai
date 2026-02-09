# apps/api/app/routers/orgs.py
"""
Organizations Router - CursorCode AI
Manages organizations (tenants): CRUD + switching.
Multi-tenant foundation: all projects/users scoped to org.
Only org_owners/admins can manage their org.
"""

import logging
from datetime import datetime
from typing import Dict, List, Annotated, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Request,
    Response,
)
from pydantic import BaseModel, Field
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter

from app.core.config import settings
from app.db.session import get_db
from app.middleware.auth import get_current_user, AuthUser, require_org_owner
from app.models.user import User
from app.models.org import Org
from app.services.logging import audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orgs", tags=["Organizations"])

# Rate limiter — uses client IP
limiter = Limiter(key_func=lambda r: r.client.host)


class OrgCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Organization name")
    slug: Optional[str] = Field(None, min_length=3, max_length=100, description="Unique slug (auto-generated if empty)")


class OrgUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    slug: Optional[str] = Field(None, min_length=3, max_length=100)


class OrgOut(BaseModel):
    id: UUID
    name: str
    slug: Optional[str]
    created_at: datetime
    updated_at: datetime
    member_count: int = 0

    class Config:
        from_attributes = True


@router.post(
    "/",
    response_model=OrgOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create new organization",
)
@limiter.limit("3/minute")
async def create_org(
    request: Request,
    payload: OrgCreate,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new organization and assign current user as org_owner.
    """
    # Check slug uniqueness if provided
    if payload.slug:
        existing = await db.scalar(select(Org).where(Org.slug == payload.slug))
        if existing:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Slug already in use")

    org = Org(
        name=payload.name,
        slug=payload.slug or f"org-{UUID().hex[:8]}",  # Auto-generate if missing
    )
    db.add(org)
    await db.flush()  # Get org.id

    # Assign current user as owner
    user = await db.get(User, UUID(current_user.id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    user.org_id = org.id
    user.roles.append("org_owner")

    await db.commit()
    await db.refresh(org)
    await db.refresh(user)

    audit_log.delay(
        user_id=current_user.id,
        action="org_created",
        metadata={"org_id": str(org.id), "name": org.name, "slug": org.slug}
    )

    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "created_at": org.created_at,
        "updated_at": org.updated_at,
        "member_count": 1,
    }


@router.get(
    "/",
    response_model=List[OrgOut],
    summary="List organizations current user belongs to",
)
async def list_orgs(
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    List all organizations the current user is a member of.
    """
    stmt = (
        select(Org)
        .join(User, User.org_id == Org.id)
        .where(User.id == UUID(current_user.id))
        .order_by(Org.name)
    )
    result = await db.execute(stmt)
    orgs = result.scalars().all()

    # Compute member count efficiently
    for org in orgs:
        count_stmt = select(func.count(User.id)).where(User.org_id == org.id)
        count = await db.scalar(count_stmt)
        org.member_count = count or 0

    return orgs


@router.get(
    "/{org_id}",
    response_model=OrgOut,
    summary="Get organization details",
)
async def get_org(
    org_id: UUID,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve organization details (must be a member).
    """
    org = await db.get(Org, org_id)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    if UUID(current_user.org_id) != org_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of this organization")

    count_stmt = select(func.count(User.id)).where(User.org_id == org_id)
    count = await db.scalar(count_stmt)
    org.member_count = count or 0

    return org


@router.patch(
    "/{org_id}",
    response_model=OrgOut,
    summary="Update organization (name/slug)",
)
@limiter.limit("3/minute")
async def update_org(
    request: Request,
    org_id: UUID,
    payload: OrgUpdate,
    current_user: Annotated[AuthUser, Depends(require_org_owner)],
    db: AsyncSession = Depends(get_db),
):
    """
    Update organization name or slug.
    Only org_owner can modify.
    """
    org = await db.get(Org, org_id)
    if not org or UUID(current_user.org_id) != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    if payload.name is not None:
        org.name = payload.name

    if payload.slug is not None:
        existing = await db.scalar(
            select(Org).where(Org.slug == payload.slug, Org.id != org_id)
        )
        if existing:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Slug already in use")
        org.slug = payload.slug

    await db.commit()
    await db.refresh(org)

    audit_log.delay(
        current_user.id,
        "org_updated",
        {"org_id": str(org_id), "changes": payload.dict(exclude_unset=True)}
    )

    return org


@router.delete(
    "/{org_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete organization",
)
@limiter.limit("1/minute")
async def delete_org(
    request: Request,
    org_id: UUID,
    current_user: Annotated[AuthUser, Depends(require_org_owner)],
    db: AsyncSession = Depends(get_db),
):
    """
    Soft-delete organization (sets deleted_at).
    Only org_owner can delete.
    """
    org = await db.get(Org, org_id)
    if not org or UUID(current_user.org_id) != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    org.deleted_at = datetime.utcnow()
    await db.commit()

    audit_log.delay(
        current_user.id,
        "org_deleted",
        {"org_id": str(org_id), "name": org.name}
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/switch/{org_id}",
    response_model=Dict[str, str],
    summary="Switch active organization",
)
@limiter.limit("5/minute")
async def switch_org(
    request: Request,
    org_id: UUID,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Switch the user's active organization.
    Future-proof for updating JWT claims on refresh.
    """
    membership = await db.scalar(
        select(User).where(User.id == UUID(current_user.id), User.org_id == org_id)
    )
    if not membership:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of this organization")

    # TODO: In future — issue new JWT with updated org_id claim

    audit_log.delay(
        current_user.id,
        "org_switched",
        {"new_org_id": str(org_id)}
    )

    return {"message": f"Switched to organization {org_id}"}
