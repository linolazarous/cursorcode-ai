# apps/api/app/models/plan.py
from sqlalchemy import Column, String, Integer, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid import uuid4
from datetime import datetime
from app.db.base import Base

class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # starter, pro, etc.
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_usd: Mapped[int] = mapped_column(Integer, nullable=False)  # cents, e.g. 999 = $9.99
    interval: Mapped[str] = mapped_column(String(20), default="month")  # month / year
    stripe_product_id: Mapped[str] = mapped_column(String(255), nullable=True)
    stripe_price_id: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Plan(name={self.name}, price=${self.price_usd/100:.2f}/{self.interval})>"
