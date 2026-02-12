"""
AuditLog model for CursorCode AI
Immutable audit trail for compliance, security, and debugging.
Records all significant actions (auth, billing, admin ops, project events, etc.).
Uses mixins from db/models/mixins.py for reusable patterns.
"""

from datetime import datetime, timezone  # ← added timezone
from typing import Dict, Optional

from sqlalchemy import String, Text, func, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base
from app.db.models.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin


class AuditLog(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """
    Audit Log Entry
    - Immutable record of user/system actions
    - Captures who, what, when, where, how
    - Supports filtering by user, action, time, IP
    - JSONB metadata for flexible, queryable context
    """

    __tablename__ = "audit_logs"
    __table_args__ = {'extend_existing': True}  # prevents duplicate table error in SQLAlchemy

    # What happened
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Action identifier (e.g. 'login_success', 'project_created', 'subscription_activated')"
    )

    # Flexible context (JSONB for efficient querying)
    event_metadata: Mapped[Dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Structured metadata (e.g. {'ip': '...', 'plan': 'pro', 'tokens': 5000})"
    )

    # Request context
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        index=True,
        comment="Client IP (IPv4 or IPv6)"
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="User-Agent header"
    )
    request_path: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="API endpoint/path that triggered the action"
    )
    request_method: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="HTTP method (GET, POST, etc.)"
    )
    request_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True,
        comment="Correlation ID (X-Request-ID) for tracing"
    )

    # Timestamps & Soft Delete (inherited from TimestampMixin + SoftDeleteMixin)
    # created_at, updated_at, deleted_at already present

    def __repr__(self) -> str:
        fields = [f"id={self.id}", f"action={self.action!r}"]
        if self.user_id:
            fields.append(f"user_id={self.user_id}")
        fields.append(f"created_at={self.created_at}")
        return f"<AuditLog({' '.join(fields)})>"

    @property
    def is_active(self) -> bool:
        """Check if the audit entry is not soft-deleted."""
        return self.deleted_at is None

    def soft_delete(self) -> None:
        """Mark entry as deleted (soft delete) — rare use case."""
        if self.deleted_at is None:
            self.deleted_at = datetime.now(timezone.utc)  # ← recommended UTC-aware assignment
