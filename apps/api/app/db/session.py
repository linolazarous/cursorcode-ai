"""
Database session management for CursorCode AI.

Features:
• Async SQLAlchemy engine
• Supabase pooled connection support
• SSL enforced
• Connection pooling
• FastAPI dependency injection
• Startup connection test
• Clean shutdown
• Production-ready stability
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sqlalchemy import text
from sqlalchemy.pool import NullPool

from app.core.config import settings


# ────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────

logger = logging.getLogger("cursorcode.db")


# ────────────────────────────────────────────────
# Engine Creation
# ────────────────────────────────────────────────

DATABASE_URL = str(settings.DATABASE_URL)

is_dev = settings.ENVIRONMENT == "development"


def create_engine() -> AsyncEngine:
    """
    Create Async SQLAlchemy Engine.

    Supabase pooled connection requires SSL.
    """

    logger.info(f"Creating database engine (env={settings.ENVIRONMENT})")

    return create_async_engine(
        DATABASE_URL,

        # Debug
        echo=is_dev,

        # Pool settings
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,

        # Supabase SSL requirement
        connect_args={
            "ssl": True,
            "server_settings": {
                "application_name": "cursorcode-api"
            },
        },

        # Prevent stale connections
        poolclass=None if not is_dev else NullPool,
    )


engine: AsyncEngine = create_engine()


# ────────────────────────────────────────────────
# Session Factory
# ────────────────────────────────────────────────

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ────────────────────────────────────────────────
# FastAPI Dependency
# ────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency.

    Usage:

    db: AsyncSession = Depends(get_db)
    """

    async with async_session_factory() as session:

        try:

            yield session

            await session.commit()

        except Exception:

            await session.rollback()

            raise

        finally:

            await session.close()


# ────────────────────────────────────────────────
# Database Health Check
# ────────────────────────────────────────────────

async def check_db_connection() -> bool:

    try:

        async with engine.connect() as conn:

            result = await conn.execute(text("SELECT 1"))

            return result.scalar() == 1

    except Exception as e:

        logger.error("Database health check failed", exc_info=True)

        return False


# ────────────────────────────────────────────────
# Startup Initialization
# ────────────────────────────────────────────────

async def init_db():

    logger.info("Testing database connection...")

    try:

        async with engine.connect() as conn:

            result = await conn.execute(text("SELECT version()"))

            version = result.scalar()

            logger.info(f"Database connected: {version}")

    except Exception:

        logger.critical(

            "DATABASE CONNECTION FAILED",

            exc_info=True

        )

        # Do not crash app
        # Supabase may be sleeping


# ────────────────────────────────────────────────
# Lifespan Manager
# ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app):

    logger.info("Starting CursorCode API...")

    await init_db()

    yield

    logger.info("Closing database engine...")

    await engine.dispose()

    logger.info("Database engine closed")


# ────────────────────────────────────────────────
# Utility
# ────────────────────────────────────────────────

def get_engine() -> AsyncEngine:

    return engine
