# apps/api/app/db/models/org.py
"""
Organization (tenant) model for CursorCode AI
Multi-tenant foundation: users, projects, billing scoped to org.
"""

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import String, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Org(Base, TimestampMixin):
    """
    Organization / Tenant Entity
    - Root of multi-tenancy in CursorCode AI
    - All resources (users, projects, billing, usage) scoped per org
    - Supports teams, soft-delete, and future team invites
    """

    __tablename__ = "orgs"
    __table_args__ = (
        Index("ix_orgs_slug", "slug", unique=True),
        Index("ix_orgs_deleted_at", "deleted_at"),
        Index("ix_orgs_name", "name"),
        {'extend_existing': True},
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
        index=True,
    )

    # Core identity
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Display name of the organization"
    )

    slug: Mapped[Optional[str]] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
        index=True,
        comment="URL-friendly identifier (auto-generated if empty)"
    )

    # Lifecycle
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        index=True,
        comment="Soft-delete timestamp (null = active)"
    )

    # Relationships
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
        status = "active" if self.deleted_at is None else f"deleted:{self.deleted_at}"
        return f"<Org(id={self.id}, name={self.name}, slug={self.slug}, status={status})>"

    @property
    def is_active(self) -> bool:
        """Check if the organization is not soft-deleted."""
        return self.deleted_at is None

    def soft_delete(self) -> None:
        """Mark organization as deleted (soft delete)."""
        if self.deleted_at is None:
            self.deleted_at = datetime.now(timezone.utc)
