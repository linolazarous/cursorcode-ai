# apps/api/app/db/models/utils.py
"""
Utility functions and helpers for SQLAlchemy models in CursorCode AI.
Contains slug generation, uniqueness checks, and other common model operations.
"""

import re
import unicodedata
import secrets
from typing import Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


# Strong typing for SQLAlchemy models
ModelT = TypeVar("ModelT", bound=DeclarativeBase)


def generate_slug(
    text: str,
    max_length: int = 100,
    prefix: Optional[str] = None,
    separator: str = "-"
) -> str:
    """
    Generate URL-safe slug from text (e.g. project title → slug).
    """

    if not text:
        return ""

    # Normalize unicode → ASCII
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

    # Replace invalid chars
    text = re.sub(r"[^a-z0-9]+", separator, text.lower())
    text = text.strip(separator)

    if prefix:
        text = f"{prefix}{text}"

    return text[:max_length]


async def is_slug_unique(
    slug: str,
    model_class: Type[ModelT],
    db: AsyncSession,                 # ✅ REQUIRED FIRST
    exclude_id: Optional[str] = None,
) -> bool:
    """
    Check if a slug is unique in the given model table.
    Optionally exclude a record ID (for updates).
    """

    stmt = select(model_class).where(model_class.slug == slug)

    if exclude_id:
        stmt = stmt.where(model_class.id != exclude_id)

    result = await db.execute(stmt)

    return result.scalar_one_or_none() is None


async def generate_unique_slug(
    text: str,
    model_class: Type[ModelT],
    db: AsyncSession,
    exclude_id: Optional[str] = None,
    max_length: int = 100,
    max_attempts: int = 10,
    suffix_length: int = 6,
    prefix: Optional[str] = None,
    separator: str = "-"
) -> str:
    """
    Generate a unique slug based on text.
    Appends short random hex suffix if collision occurs.
    """

    base_slug = generate_slug(
        text=text,
        max_length=max_length,
        prefix=prefix,
        separator=separator
    )

    # First attempt without suffix
    if await is_slug_unique(
        slug=base_slug,
        model_class=model_class,
        db=db,
        exclude_id=exclude_id,
    ):
        return base_slug

    # Retry with suffix
    for _ in range(max_attempts):

        # More efficient than token_hex slicing
        suffix = secrets.token_urlsafe(suffix_length)[:suffix_length]

        candidate = f"{base_slug}-{suffix}"

        if len(candidate) > max_length:
            candidate = candidate[:max_length]

        if await is_slug_unique(
            slug=candidate,
            model_class=model_class,
            db=db,
            exclude_id=exclude_id,
        ):
            return candidate

    raise ValueError(
        f"Could not generate unique slug for '{text}' "
        f"after {max_attempts} attempts."
    )
