# apps/api/app/db/models/plan.py
"""
SQLAlchemy Plan Model - CursorCode AI
Stores billing plan definitions with dynamic Stripe Product/Price IDs.
Auto-created prices are cached here for idempotency and fast lookup.
Uses mixins from db/models/mixins.py for reusable patterns.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base
from app.db.models.mixins import UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin
from app.db.models.utils import generate_unique_slug


class Plan(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """
    Billing Plan Entity
    - Defines available subscription tiers (starter, pro, ultra, etc.)
    - Stores auto-generated Stripe Product & Price IDs
    - Used for dynamic checkout session creation
    - Supports future features like credit allowances, feature lists
    """
    __tablename__ = "plans"
    __table_args__ = {'extend_existing': True}  # ← FINAL FIX: prevents duplicate table error in SQLAlchemy

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

    # Lifecycle (inherited from SoftDeleteMixin)
    # deleted_at already present

    def __repr__(self) -> str:
        price = f"${self.price_usd:.2f}" if self.price_usd_cents else "$0.00"
        status = "active" if self.is_active else f"deleted:{self.deleted_at}"
        return f"<Plan(name={self.name}, display={self.display_name}, price={price}/{self.interval}, status={status})>"

    @property
    def price_usd(self) -> float:
        """Human-readable price in USD (float)."""
        return self.price_usd_cents / 100.0 if self.price_usd_cents is not None else 0.0

    @property
    def is_free(self) -> bool:
        """Quick check if this is the free tier."""
        return self.price_usd_cents == 0

    @classmethod
    async def create_unique_slug(cls, display_name: str, db) -> str:
        """Generate unique slug for this plan based on display name (future use)."""
        return await generate_unique_slug(display_name, cls, db=db)
