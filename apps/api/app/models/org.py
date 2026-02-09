# apps/api/app/models/org.py
"""
Organization (tenant) model for CursorCode AI
Multi-tenant foundation: users, projects, billing scoped to org.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Org(Base):
    """
    Organization entity.
    Represents a tenant/workspace in CursorCode AI.
    All resources (users, projects, billing) are scoped to an organization.
    """

    __tablename__ = "orgs"
    __table_args__ = {'extend_existing': True}  # Prevents duplicate table definition errors

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

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

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
        comment="When the organization was created"
    )

    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last time the organization was updated"
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        index=True,
        comment="Soft-delete timestamp (null = active)"
    )

    # Optional: future fields (uncomment/add when needed)
    # description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    # owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    def __repr__(self) -> str:
        return f"Org(id={self.id}, name='{self.name}', slug='{self.slug}', active={self.is_active()})"

    def is_active(self) -> bool:
        """Check if the organization is not soft-deleted."""
        return self.deleted_at is None

    def soft_delete(self) -> None:
        """Mark organization as deleted (soft delete)."""
        self.deleted_at = datetime.utcnow()
