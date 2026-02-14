"""
Database session management for CursorCode AI.

Production-grade (Supabase + Render + asyncpg)

Features:
• Async SQLAlchemy engine
• Supabase pooled connection optimized
• Proper SSLContext (fixes CERTIFICATE_VERIFY_FAILED)
• Stable connection pooling
• FastAPI dependency injection
• Health checks
• Startup connection verification
• Graceful shutdown
"""

import logging
import ssl
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sqlalchemy import text

from app.core.config import settings


# ────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────

logger = logging.getLogger("cursorcode.db")


# ────────────────────────────────────────────────
# SSL Context (CRITICAL FIX)
# ────────────────────────────────────────────────
# Supabase requires proper SSL context, NOT ssl=True

ssl_context = ssl.create_default_context()

ssl_context.check_hostname = True
ssl_context.verify_mode = ssl.CERT_REQUIRED


# ────────────────────────────────────────────────
# Engine Creation
# ────────────────────────────────────────────────

DATABASE_URL = str(settings.DATABASE_URL)

is_dev = settings.is_dev


def create_engine() -> AsyncEngine:
    """
    Create Async SQLAlchemy Engine.

    Supabase pooler compatible.
    """

    logger.info(
        "Creating database engine",
        extra={
            "environment": settings.ENVIRONMENT,
            "database_host": settings.DATABASE_URL.host,
        },
    )

    return create_async_engine(
        DATABASE_URL,

        # Debug logging
        echo=is_dev,

        # Connection pool
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,

        # Critical: Supabase SSL fix
        connect_args={
            "ssl": ssl_context,
            "server_settings": {
                "application_name": "cursorcode-api"
            },
        },
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
    FastAPI DB dependency.

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
# Health Check
# ────────────────────────────────────────────────

async def check_db_connection() -> bool:

    try:

        async with engine.connect() as conn:

            result = await conn.execute(text("SELECT 1"))

            return result.scalar() == 1

    except Exception:

        logger.error(
            "Database health check failed",
            exc_info=True
        )

        return False


# ────────────────────────────────────────────────
# Startup Test
# ────────────────────────────────────────────────

async def init_db():

    logger.info("Testing database connection...")

    try:

        async with engine.connect() as conn:

            result = await conn.execute(text("SELECT version()"))

            version = result.scalar()

            logger.info(
                "Database connected successfully",
                extra={"postgres_version": version}
            )

    except Exception:

        logger.critical(
            "DATABASE CONNECTION FAILED",
            exc_info=True
        )


# ────────────────────────────────────────────────
# FastAPI Lifespan
# ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app):

    logger.info("CursorCode API starting")

    await init_db()

    yield

    logger.info("Closing database engine")

    await engine.dispose()

    logger.info("Database engine closed")


# ────────────────────────────────────────────────
# Utility
# ────────────────────────────────────────────────

def get_engine() -> AsyncEngine:

    return engine
