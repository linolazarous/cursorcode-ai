# apps/api/app/db/models/org.py
"""
Organization (tenant) model for CursorCode AI
Multi-tenant foundation: users, projects, billing scoped to org.
Uses mixins from db/models/mixins.py for reusable patterns.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base
from app.db.models.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, SlugMixin
from app.db.models.utils import generate_unique_slug


class Org(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, SlugMixin):
    """
    Organization / Tenant Entity
    - Root of multi-tenancy in CursorCode AI
    - All resources (users, projects, billing, usage) scoped per org
    - Supports teams, soft-delete, and future team invites
    """
    __tablename__ = "orgs"

    # Core identity (slug from SlugMixin)
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Display name of the organization"
    )

    # Relationships (forward refs via string names — no import needed)
    users: Mapped[List["User"]] = relationship(
        "User",
        back_populates="org",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    projects: Mapped[List["Project"]] = relationship(
        "Project",
        back_populates="org",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    # Optional future fields (uncomment when implemented)
    # description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    # owner_id: Mapped[Optional[str]] = mapped_column(
    #     UUID(as_uuid=True),
    #     ForeignKey("users.id"),
    #     nullable=True,
    #     index=True
    # )

    def __repr__(self) -> str:
        status = "active" if self.is_active else f"deleted:{self.deleted_at}"
        return f"<Org(id={self.id}, name={self.name}, slug={self.slug}, status={status})>"

    @classmethod
    async def create_unique_slug(cls, name: str, db) -> str:
        """Generate unique slug for this organization based on name."""
        return await generate_unique_slug(name, cls, db=db)
