# apps/api/app/db/base.py
"""
SQLAlchemy declarative base for CursorCode AI.
All models inherit from this Base class.

This file is kept minimal:
- Defines the abstract Base (never mapped to a table)
- Provides safe __repr__ / __str__ helpers
- Global __table_args__ with extend_existing=True to prevent duplicate table errors during import
- All reusable patterns (timestamps, UUID, soft-delete, audit, slug, etc.) are in db/models/mixins.py and utils.py

Do NOT add table-specific logic or mixins here — keep models clean and modular.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Abstract base class for all SQLAlchemy models in CursorCode AI.

    Features:
    - __abstract__ = True → prevents Base from being mapped as a table
    - Global __table_args__ with extend_existing=True — fixes duplicate table errors when models are imported multiple times (common with aggregators)
    - No automatic table name generation (define __tablename__ explicitly in each model)
    - Safe __repr__ / __str__ helpers for debugging/logs

    All concrete models should inherit from Base + mixins from db/models/mixins.py
    """
    __abstract__ = True

    # Global table args for ALL models — prevents duplicate definition errors
    __table_args__ = {
        "extend_existing": True,  # ← FINAL FIX: allows re-definition of tables during import
        # "schema": "public",     # uncomment if using PostgreSQL schemas
    }

    def __repr__(self) -> str:
        """Safe, readable representation (avoids loading large relationships or lazy fields)."""
        fields = ", ".join(
            f"{k}={v!r}"
            for k, v in self.__dict__.items()
            if not k.startswith("_") and v is not None
        )
        return f"{self.__class__.__name__}({fields})"

    def __str__(self) -> str:
        """Human-readable string representation (useful in logs and debugging)."""
        return self.__repr__()
