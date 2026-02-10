# apps/api/app/routers/projects.py
"""
Projects Router - CursorCode AI
CRUD operations for AI-generated projects.
Includes credit checks, orchestration trigger, multi-tenant scoping, audit logging.
Supports real-time streaming via SSE for orchestration progress.
"""

import logging
from datetime import datetime
from typing import List, Annotated, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    BackgroundTasks,
    Query,
    Request,
    Response,
)
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.db.session import get_db
from app.middleware.auth import get_current_user, AuthUser
from app.models.project import Project, ProjectStatus
from app.services.billing import deduct_credits
from app.services.email import send_deployment_success_email
from app.services.logging import audit_log
from app.ai.orchestrator import stream_orchestration  # ← Streaming function

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])

security = HTTPBearer(auto_error=False)

# Rate limit: 5 projects per minute per user (not IP)
limiter = Limiter(key_func=lambda r: r.state.user_id if hasattr(r.state, "user_id") else get_remote_address())


class ProjectCreate(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=4000, description="Natural language description of the app")
    title: Optional[str] = Field(None, max_length=255)


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    status: Optional[ProjectStatus] = None


class ProjectOut(BaseModel):
    id: UUID
    title: Optional[str]
    prompt: str
    status: ProjectStatus
    deploy_url: Optional[str]
    preview_url: Optional[str]
    code_repo_url: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post(
    "/",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create new AI-generated project (streaming via SSE)",
)
@limiter.limit("5/minute")
async def create_project(
    request: Request,
    payload: ProjectCreate,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new project from prompt.
    - Deducts credits
    - Triggers agent orchestration
    - Returns project metadata immediately
    - Client can connect to /projects/{id}/stream for real-time tokens
    """
    # Credit check & atomic deduction
    success, msg = await deduct_credits(
        user_id=current_user.id,
        amount=10,  # TODO: make dynamic based on user_tier / complexity
        reason=f"Project creation: {payload.prompt[:50]}...",
        db=db,
    )
    if not success:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, msg)

    project = Project(
        prompt=payload.prompt,
        title=payload.title or f"Project {UUID().hex[:8]}",
        status=ProjectStatus.PENDING,
        user_id=UUID(current_user.id),
        org_id=UUID(current_user.org_id),
    )

    db.add(project)
    await db.commit()
    await db.refresh(project)

    # Trigger background orchestration (non-streaming Celery fallback)
    background_tasks.add_task(
        run_agent_graph_task.delay,
        project_id=str(project.id),
        prompt=payload.prompt,
        user_id=current_user.id,
        org_id=current_user.org_id,
    )

    # Audit
    audit_log.delay(
        user_id=current_user.id,
        action="project_created",
        metadata={
            "project_id": str(project.id),
            "title": project.title,
            "prompt_length": len(payload.prompt),
            "credits_deducted": 10,
        },
        request=request,
    )

    # Email notification (async)
    background_tasks.add_task(
        send_deployment_success_email,
        email=current_user.email,
        project_title=project.title or "Untitled Project",
        deploy_url=None,  # Updated later
    )

    return project


@router.get(
    "/{project_id}/stream",
    summary="Stream real-time orchestration progress (SSE)",
    response_class=StreamingResponse,
)
@limiter.limit("10/minute")
async def stream_project(
    project_id: UUID,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Server-Sent Events (SSE) endpoint for real-time token streaming.
    Client connects here after creating a project.
    """
    project = await db.get(Project, project_id)
    if not project or project.user_id != UUID(current_user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found or not owned")

    if project.status not in [ProjectStatus.PENDING, ProjectStatus.RUNNING]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Project not in streamable state")

    async def sse_generator():
        yield "data: [START] Orchestration started\n\n"

        async for chunk in stream_orchestration(
            project_id=str(project.id),
            prompt=project.prompt,
            user_id=current_user.id,
            org_id=current_user.org_id,
            user_tier="starter",  # TODO: from user profile
        ):
            yield f"data: {chunk}\n\n"

        yield "data: [COMPLETE] Orchestration finished\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Important for Render/NGINX
        }
    )


@router.get(
    "/",
    response_model=List[ProjectOut],
    summary="List user's projects (paginated)",
)
async def list_projects(
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[ProjectStatus] = None,
):
    stmt = (
        select(Project)
        .where(Project.user_id == UUID(current_user.id))
        .order_by(Project.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if status:
        stmt = stmt.where(Project.status == status)

    result = await db.execute(stmt)
    projects = result.scalars().all()

    return projects


@router.get(
    "/{project_id}",
    response_model=ProjectOut,
    summary="Get single project details",
)
async def get_project(
    project_id: UUID,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project or project.user_id != UUID(current_user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    return project


@router.patch(
    "/{project_id}",
    response_model=ProjectOut,
    summary="Update project (title, status)",
)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project or project.org_id != UUID(current_user.org_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    if payload.title:
        project.title = payload.title
    if payload.status:
        project.status = payload.status

    await db.commit()
    await db.refresh(project)

    audit_log.delay(
        user_id=current_user.id,
        action="project_updated",
        metadata={"project_id": str(project_id), "changes": payload.dict(exclude_unset=True)}
    )

    return project


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete project (soft delete)",
)
async def delete_project(
    project_id: UUID,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project or project.user_id != UUID(current_user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    project.deleted_at = datetime.utcnow()
    await db.commit()

    audit_log.delay(
        user_id=current_user.id,
        action="project_deleted",
        metadata={"project_id": str(project_id)}
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
