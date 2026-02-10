# apps/api/app/models/plan.py
"""
SQLAlchemy Plan Model - CursorCode AI
Stores billing plan definitions with dynamic Stripe Product/Price IDs.
Auto-created prices are cached here for idempotency and fast lookup.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Plan(Base, TimestampMixin):
    """
    Billing Plan Entity
    - Defines available subscription tiers (starter, pro, ultra, etc.)
    - Stores auto-generated Stripe Product & Price IDs
    - Used for dynamic checkout session creation
    - Supports future features like credit allowances, feature lists
    """

    __tablename__ = "plans"
    __table_args__ = (
        Index("ix_plans_name", "name", unique=True),
        Index("ix_plans_stripe_price_id", "stripe_price_id"),
        Index("ix_plans_deleted_at", "deleted_at"),
        {'extend_existing': True},
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
        index=True,
    )

    # Plan identifier (used in code, URLs, metadata)
    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Internal unique key (e.g. 'starter', 'pro', 'ultra')"
    )

    # Display name for UI/emails
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable name (e.g. 'Starter Plan', 'Pro Plan')"
    )

    # Pricing (in USD cents)
    price_usd_cents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Price in USD cents (e.g. 999 = $9.99)"
    )

    # Billing cycle
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
        unique=True,
        comment="Stripe Product ID"
    )
    stripe_price_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        comment="Stripe recurring Price ID"
    )

    # Plan status & visibility
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether this plan is available for new signups"
    )

    # Optional future fields (uncomment when implemented)
    # monthly_credits: Mapped[Optional[int]] = mapped_column(
    #     Integer, nullable=True, comment="Monthly credits included"
    # )
    # features: Mapped[Optional[List[str]]] = mapped_column(
    #     JSON, nullable=True, comment="Feature list (e.g. ['priority support', 'custom domain'])"
    # )
    # max_projects: Mapped[Optional[int]] = mapped_column(
    #     Integer, nullable=True, comment="Max concurrent projects"
    # )

    # Lifecycle
    deleted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True, index=True)

    def __repr__(self) -> str:
        price = f"${self.price_usd:.2f}" if self.price_usd_cents else "$0.00"
        return f"<Plan(name={self.name}, display={self.display_name}, price={price}/{self.interval})>"

    @property
    def price_usd(self) -> float:
        """Human-readable price in USD (float)."""
        return self.price_usd_cents / 100.0 if self.price_usd_cents is not None else 0.0

    @property
    def is_free(self) -> bool:
        """Quick check if this is the free tier."""
        return self.price_usd_cents == 0
