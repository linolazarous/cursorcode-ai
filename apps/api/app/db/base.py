# apps/api/app/db/base.py
"""
SQLAlchemy declarative base and common mixins for CursorCode AI.
All models should inherit from Base (and optionally TimestampMixin).

This file defines:
- Abstract Base class (never mapped to a table)
- TimestampMixin for automatic created_at / updated_at
- No automatic table name generation (explicit __tablename__ is safer)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Abstract base class for all SQLAlchemy models in CursorCode AI.

    Features:
    - __abstract__ = True → prevents Base from being mapped as a table
    - Common place for global conventions (e.g. schema, future extensions)
    - No automatic table name generation (define __tablename__ explicitly in models)
    """

    __abstract__ = True

    # Optional future extensions (uncomment when needed):
    # __table_args__ = {"schema": "public"}  # if using schemas

    def __repr__(self) -> str:
        """Safe, readable representation (avoids loading large relationships)."""
        fields = ", ".join(
            f"{k}={v!r}"
            for k, v in self.__dict__.items()
            if not k.startswith("_") and v is not None
        )
        return f"{self.__class__.__name__}({fields})"

    def __str__(self) -> str:
        """Human-readable string (useful in logs)."""
        return self.__repr__()


# ────────────────────────────────────────────────
# Timestamp Mixin (recommended for most models)
# ────────────────────────────────────────────────
class TimestampMixin:
    """
    Mixin that adds automatic created_at / updated_at timestamps.

    Usage:
        class User(Base, TimestampMixin):
            ...

    Benefits:
    - Server-side defaults and updates (no Python-side code needed)
    - Indexed updated_at (fast for "recently modified" queries)
    """

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
        comment="When the record was created (UTC)"
    )

    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,  # ← Very useful for sorting / filtering recent changes
        comment="When the record was last updated (UTC)"
    )
