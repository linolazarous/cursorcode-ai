# apps/api/app/models/plan.py
"""
SQLAlchemy Plan Model - CursorCode AI
Stores billing plan definitions with dynamic Stripe Product/Price IDs.
Auto-created prices are cached here for idempotency and fast lookup.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Plan(Base):
    """
    Billing Plan Entity
    - Defines available subscription tiers (starter, pro, ultra, etc.)
    - Stores auto-generated Stripe Product & Price IDs
    - Used for dynamic checkout session creation
    - Supports future features like credit allowances, features list
    """
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
        index=True,
    )

    # Plan identifier (used in code & URLs)
    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )  # e.g. "starter", "pro", "ultra"

    # Display name for UI/emails
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # e.g. "Starter Plan", "Pro Plan"

    # Pricing in USD cents (e.g. 999 = $9.99)
    price_usd_cents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Recurring interval
    interval: Mapped[str] = mapped_column(
        String(20),
        default="month",
        nullable=False,
    )  # "month" or "year"

    # Stripe integration
    stripe_product_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    stripe_price_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Plan status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Optional: monthly credit allowance for this plan
    monthly_credits: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )  # e.g. 1000 credits/mo for Pro

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        price = self.price_usd_cents / 100 if self.price_usd_cents else 0
        return f"<Plan(name={self.name}, display={self.display_name}, price=${price:.2f}/{self.interval})>"

    @property
    def price_usd(self) -> float:
        """Human-readable price in USD (float)."""
        return self.price_usd_cents / 100 if self.price_usd_cents else 0.0
