# apps/api/app/db/base.py
"""
SQLAlchemy declarative base and metadata for CursorCode AI.
All models inherit from this Base class.

This file defines:
- Base declarative class
- Common table name convention (optional)
- Timestamp mixin pattern (optional, can be used by models)
"""

from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models in CursorCode AI.
    
    Features:
    - Automatic table name generation (lowercase class name + 's')
    - Common timestamp columns can be added via mixin if desired
    """

    # Optional: automatically generate table names like "user" → "users"
    # Remove or comment out if you prefer explicit __tablename__
    @classmethod
    def __tablename__(cls) -> str:
        return cls.__name__.lower() + "s"

    # Optional: common timestamp columns (you can inherit this in models)
    # Example usage in a model:
    # class User(Base):
    #     created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    #     updated_at: Mapped[datetime] = mapped_column(onupdate=func.now(), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Optional: helper method to get column names (useful for migrations / audits)
    @classmethod
    def get_column_names(cls) -> list[str]:
        return [c.key for c in cls.__table__.columns]

    def __repr__(self) -> str:
        # Nice repr for debugging: User(id=123, email='user@example.com')
        fields = ", ".join(f"{k}={v!r}" for k, v in self.__dict__.items() if not k.startswith("_"))
        return f"{self.__class__.__name__}({fields})"
