# apps/api/app/models/audit.py
"""
AuditLog model for CursorCode AI
Tracks user actions, admin operations, auth events, API calls, etc.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.user import User


class AuditLog(Base):
    """
    Audit log entry.
    Records important actions with context (who, what, when, where, how).
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Who performed the action
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
        comment="ID of the user who performed the action (null for system/anonymous)"
    )

    # What happened
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Action identifier (e.g. 'login_success', '2fa_enabled', 'project_created')"
    )

    # Additional context (JSON)
    metadata: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        server_default="{}",
        comment="Flexible JSON metadata (e.g. {'ip': '...', 'details': {...}})"
    )

    # Where / How (request info)
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="Client IP address (IPv4 or IPv6)"
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="User-Agent header from the request"
    )
    request_path: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="API endpoint or path that triggered the action"
    )
    request_method: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="HTTP method (GET, POST, etc.)"
    )

    # When
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="Timestamp when the action occurred"
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last update timestamp (useful if audit log can be modified)"
    )

    def __repr__(self) -> str:
        fields = []
        for attr in ['id', 'user_id', 'action', 'created_at']:
            value = getattr(self, attr, None)
            if value is not None:
                fields.append(f"{attr}={value!r}")
        return f"AuditLog({', '.join(fields)})"

    def __str__(self) -> str:
        return self.__repr__()
