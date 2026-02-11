# apps/api/app/db/models/mixins.py
"""
Reusable SQLAlchemy mixins for CursorCode AI models.
These mixins provide common patterns used across entities:
- UUID primary key
- Soft-delete support
- Audit fields (created_by, updated_by)
- Slug field (with uniqueness helper in utils.py)
- Timestamps (moved from base.py to here for consistency)

Usage example:
    class MyModel(Base, UUIDMixin, SoftDeleteMixin, AuditMixin):
        ...
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4  # ← FIXED: import uuid4 here

from sqlalchemy import String, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UUIDMixin:
    """
    Mixin that uses UUIDv4 as primary key instead of autoincrement int.
    Recommended default for all models in distributed systems (no conflicts, easier sharding).
    """
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,  # ← Now works
        server_default=func.gen_random_uuid(),
        index=True,
        comment="Unique identifier (UUIDv4)"
    )


class SoftDeleteMixin:
    """
    Mixin for soft-delete support via deleted_at timestamp.
    Allows logical deletion without data loss (compliance & recovery friendly).
    """
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        index=True,
        comment="Soft-delete timestamp (null = active)"
    )

    @property
    def is_active(self) -> bool:
        """Check if record is not soft-deleted."""
        return self.deleted_at is None

    def soft_delete(self) -> None:
        """Mark record as soft-deleted."""
        if self.deleted_at is None:
            self.deleted_at = datetime.now(timezone.utc)


class AuditMixin:
    """
    Mixin for audit trail fields (who created/updated the record).
    Useful for compliance, debugging, and traceability.
    Requires User model to exist (references users.id).
    """
    created_by_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User who created this record (null = system)"
    )

    updated_by_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User who last updated this record (null = system)"
    )


class SlugMixin:
    """
    Mixin for URL-friendly slug field with uniqueness constraint.
    Useful for organizations, projects, public pages, etc.
    Use generate_unique_slug() from utils.py to create safe slugs.
    """
    slug: Mapped[Optional[str]] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
        index=True,
        comment="URL-friendly identifier (auto-generated if empty)"
    )
