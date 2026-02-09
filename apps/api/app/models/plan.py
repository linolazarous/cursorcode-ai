# apps/api/app/models/plan.py
"""
SQLAlchemy Plan Model - CursorCode AI
Stores billing plan definitions with dynamic Stripe Product/Price IDs.
Auto-created prices are cached here for idempotency and fast lookup.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Index, Integer, String, func
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

    __table_args__ = (
        Index("ix_plans_name", "name", unique=True),
        {'extend_existing': True},  # Safeguard against duplicate table registration
    )

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
        comment="Internal plan key (e.g. 'starter', 'pro', 'ultra')"
    )

    # Display name for UI/emails
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable name (e.g. 'Starter Plan', 'Pro Plan')"
    )

    # Pricing in USD cents (e.g. 999 = $9.99)
    price_usd_cents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Price in USD cents (smallest unit)"
    )

    # Recurring interval
    interval: Mapped[str] = mapped_column(
        String(20),
        default="month",
        nullable=False,
        comment="'month' or 'year'"
    )

    # Stripe integration
    stripe_product_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Stripe Product ID"
    )
    stripe_price_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Stripe Price ID for recurring billing"
    )

    # Plan status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether this plan is available for new signups"
    )

    # Optional: monthly credit allowance for this plan
    monthly_credits: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Monthly credits included (null = unlimited or custom)"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
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
