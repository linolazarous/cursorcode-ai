# apps/api/app/db/models/user.py
"""
SQLAlchemy Models - Users & Organizations
Core multi-tenant foundation for CursorCode AI (2026 production standards).
Uses mixins from db/models/mixins.py for reusable patterns.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.models.mixins import UUIDMixin, SoftDeleteMixin, AuditMixin, SlugMixin
from app.db.models.utils import generate_unique_slug

from . import UserRole  # Enum from same package


class Org(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """
    Organization / Tenant
    - Root of multi-tenancy
    - Billing, projects, and usage scoped per org
    - Supports teams (multiple users)
    """
    __tablename__ = "orgs"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True, index=True)

    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User", back_populates="org", cascade="all, delete-orphan"
    )
    projects: Mapped[List["Project"]] = relationship(
        "Project", back_populates="org", cascade="all, delete-orphan"
    )

    @classmethod
    async def create_unique_slug(cls, name: str, db) -> str:
        """Generate unique slug for this organization."""
        return await generate_unique_slug(name, cls, db=db)

    def __repr__(self) -> str:
        return f"<Org(id={self.id}, name={self.name}, slug={self.slug}, active={self.is_active})>"


class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """
    User Account (multi-tenant)
    - Belongs to exactly one Org
    - Has RBAC roles (scoped to org)
    - Full billing, 2FA, verification, reset support
    """
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True  # Null for OAuth-only users
    )

    # Verification & Reset
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    verification_expires: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    reset_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Hashed
    reset_expires: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # 2FA (TOTP)
    totp_secret: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_backup_codes: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True  # Hashed backup codes
    )

    # RBAC & Tenant
    roles: Mapped[List[str]] = mapped_column(
        JSON,
        default=["user"],
        server_default="['user']",
        nullable=False
    )
    org_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org: Mapped["Org"] = relationship("Org", back_populates="users")

    # Stripe Billing
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    plan: Mapped[str] = mapped_column(String(50), default="starter", nullable=False)
    credits: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    subscription_status: Mapped[str] = mapped_column(
        String(50), default="inactive", nullable=False
    )

    # Relationships
    projects: Mapped[List["Project"]] = relationship(
        "Project", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, email={self.email}, "
            f"org_id={self.org_id}, plan={self.plan}, "
            f"credits={self.credits}, active={self.is_active})>"
        )

    @property
    def is_active(self) -> bool:
        """Account is usable (verified and not deleted)."""
        return self.is_verified and self.deleted_at is None

    def check_password(self, password: str) -> bool:
        """Verify plain password against hashed one."""
        if not self.hashed_password:
            return False
        from argon2 import PasswordHasher
        try:
            return PasswordHasher().verify(self.hashed_password, password)
        except Exception:
            return False

    def generate_totp_uri(self) -> Optional[str]:
        """Generate TOTP provisioning URI for authenticator apps."""
        if not self.totp_secret:
            return None
        import pyotp
        return pyotp.totp.TOTP(self.totp_secret).provisioning_uri(
            name=self.email,
            issuer_name="CursorCode AI"
            )
