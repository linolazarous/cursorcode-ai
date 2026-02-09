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
    """

    __tablename__ = "orgs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True, index=True)

    def __repr__(self) -> str:
        return f"Org(id={self.id}, name='{self.name}', slug='{self.slug}')"

    def is_active(self) -> bool:
        return self.deleted_at is None
