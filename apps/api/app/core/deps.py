"""
Centralized FastAPI dependencies for the CursorCode AI API.
All reusable dependencies (db session, current user, admin checks, etc.) are defined here.
"""

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

from app.core.config import settings
from app.db.session import async_session_factory, get_db
from app.middleware.auth import get_current_user, AuthUser, require_admin, require_org_owner
from sqlalchemy.ext.asyncio import AsyncSession

# ────────────────────────────────────────────────
# Common dependencies (use these in routers via Annotated)
# ────────────────────────────────────────────────

# Database session (async)
DBSession = Annotated[AsyncSession, Depends(get_db)]

# Current authenticated user (from JWT / middleware)
CurrentUser = Annotated[AuthUser, Depends(get_current_user)]

# Current user must be admin
CurrentAdminUser = Annotated[AuthUser, Depends(require_admin)]

# Current user must be org owner
CurrentOrgOwnerUser = Annotated[AuthUser, Depends(require_org_owner)]

# Optional current user (for public endpoints that still want context if logged in)
OptionalCurrentUser = Annotated[Optional[AuthUser], Depends(get_current_user)]

# Rate limiting key functions (used with slowapi)
def get_remote_address(request: Request) -> str:
    """Default IP-based rate limiting key."""
    return request.client.host

def get_user_id_or_ip(request: Request) -> str:
    """Prefer authenticated user ID, fallback to IP."""
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "id"):
        return str(user.id)
    return request.client.host

# Bearer token scheme (for optional auth endpoints)
security = HTTPBearer(auto_error=False)


# ────────────────────────────────────────────────
# Optional: Add more specialized dependencies here
# ────────────────────────────────────────────────

async def get_db_session() -> AsyncSession:
    """
    Low-level DB session generator (used internally by get_db).
    Usually not needed directly — prefer DBSession Annotated type.
    """
    async with async_session_factory() as session:
        yield session


def require_authenticated_user(current_user: CurrentUser) -> AuthUser:
    """
    Explicit dependency to raise 401 if user is not authenticated.
    Useful when you want to force login even if the route allows optional auth.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


# Example usage in a router:
"""
from app.core.deps import DBSession, CurrentUser, CurrentAdminUser

@router.get("/users/me")
async def read_users_me(
    current_user: CurrentUser,
    db: DBSession,
):
    return current_user
"""
