# apps/api/app/db/models/utils.py
"""
Utility functions and helpers for SQLAlchemy models in CursorCode AI.
Contains slug generation, uniqueness checks, and other common model operations.
"""

import re
import unicodedata
import secrets
from typing import Optional, Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


def generate_slug(
    text: str,
    max_length: int = 100,
    prefix: Optional[str] = None,
    separator: str = "-"
) -> str:
    """
    Generate URL-safe slug from text (e.g. project title → slug).

    Args:
        text: Input string (title, name, etc.)
        max_length: Maximum length of slug (default 100)
        prefix: Optional prefix (e.g. "proj-")
        separator: Character between words (default "-")

    Returns:
        Clean, URL-safe slug (lowercase, hyphens, no special chars)

    Example:
        generate_slug("Hello World Project!") → "hello-world-project"
        generate_slug("My Team", prefix="team-") → "team-my-team"
    """
    if not text:
        return ""

    # Normalize unicode → ASCII, remove accents
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

    # Lowercase, replace non-alphanum with separator
    text = re.sub(r"[^a-z0-9]+", separator, text.lower())

    # Strip leading/trailing separators
    text = text.strip(separator)

    # Truncate (leave room for suffix if needed)
    text = text[:max_length]

    # Add prefix if provided
    if prefix:
        text = f"{prefix}{text}"

    return text


async def is_slug_unique(
    slug: str,
    model_class: Type,
    exclude_id: Optional[str] = None,
    db: AsyncSession
) -> bool:
    """
    Check if a slug is unique in the given model table.
    Optionally exclude a record ID (for updates).

    Args:
        slug: Slug to check
        model_class: SQLAlchemy model class (e.g. Org, Project)
        exclude_id: UUID of record to exclude (for update case)
        db: Async DB session

    Returns:
        True if slug is unique, False if taken
    """
    stmt = select(model_class).where(model_class.slug == slug)

    if exclude_id:
        stmt = stmt.where(model_class.id != exclude_id)

    result = await db.execute(stmt)
    return result.scalar_one_or_none() is None


async def generate_unique_slug(
    text: str,
    model_class: Type,
    db: AsyncSession,                # Required first (no default)
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

    Args:
        text: Base text (e.g. title, name)
        model_class: SQLAlchemy model class
        db: Async DB session (required)
        exclude_id: UUID to exclude (for updates)
        max_length: Max slug length
        max_attempts: Max retries before raising error
        suffix_length: Length of random hex suffix
        prefix: Optional prefix (e.g. "proj-")
        separator: Word separator (default "-")

    Returns:
        Unique slug

    Raises:
        ValueError if no unique slug found after max_attempts
    """
    base_slug = generate_slug(text, max_length=max_length, prefix=prefix, separator=separator)

    if await is_slug_unique(base_slug, model_class, exclude_id, db):
        return base_slug

    for _ in range(max_attempts):
        suffix = secrets.token_hex(suffix_length)[:suffix_length]
        candidate = f"{base_slug}-{suffix}"
        if len(candidate) > max_length:
            candidate = candidate[:max_length]
        if await is_slug_unique(candidate, model_class, exclude_id, db):
            return candidate

    raise ValueError(
        f"Could not generate unique slug for '{text}' after {max_attempts} attempts. "
        f"Last tried: {candidate}"
    )
