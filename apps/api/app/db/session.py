"""
Database session management for CursorCode AI.

Production-grade (Supabase + Render + asyncpg)

Fully optimized for:

• Supabase pooled connection
• Render deployment
• asyncpg driver
• SSL verification
• FastAPI dependency injection
• Health checks
• Lifespan startup/shutdown
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


# ─────────────────────────────────────
# Logging
# ─────────────────────────────────────

logger = logging.getLogger("cursorcode.db")


# ─────────────────────────────────────
# SSL Context (Supabase REQUIRED)
# ─────────────────────────────────────

ssl_context = ssl.create_default_context()

ssl_context.check_hostname = True
ssl_context.verify_mode = ssl.CERT_REQUIRED


# ─────────────────────────────────────
# Database URL
# ─────────────────────────────────────

DATABASE_URL = str(settings.DATABASE_URL)


# ─────────────────────────────────────
# Engine Creation
# ─────────────────────────────────────


def create_engine() -> AsyncEngine:

    logger.info(
        "Creating database engine",
        extra={
            "environment": settings.ENVIRONMENT,
            "host": settings.DATABASE_URL.host,
        },
    )

    return create_async_engine(
        DATABASE_URL,

        # Logging
        echo=settings.is_dev,

        # Pool settings (SUPABASE SAFE)
        pool_size=3,
        max_overflow=5,
        pool_timeout=30,
        pool_recycle=1800,

        # VERY IMPORTANT
        pool_pre_ping=True,

        # asyncpg settings
        connect_args={
            "ssl": ssl_context,

            "statement_cache_size": 0,

            "server_settings": {
                "application_name": "cursorcode-api"
            },
        },
    )


engine: AsyncEngine = create_engine()


# ─────────────────────────────────────
# Session Factory
# ─────────────────────────────────────

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


# ─────────────────────────────────────
# FastAPI Dependency
# ─────────────────────────────────────


async def get_db() -> AsyncGenerator[AsyncSession, None]:

    async with async_session_factory() as session:

        try:

            yield session

        except Exception:

            await session.rollback()

            raise

        finally:

            await session.close()


# ─────────────────────────────────────
# Health Check
# ─────────────────────────────────────


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


# ─────────────────────────────────────
# Startup Test
# ─────────────────────────────────────


async def init_db():

    logger.info("Testing database connection")

    try:

        async with engine.connect() as conn:

            result = await conn.execute(
                text("SELECT version()")
            )

            version = result.scalar()

            logger.info(
                "Database connected",
                extra={"version": version}
            )

    except Exception:

        logger.critical(
            "DATABASE CONNECTION FAILED",
            exc_info=True
        )


# ─────────────────────────────────────
# FastAPI Lifespan
# ─────────────────────────────────────


@asynccontextmanager
async def lifespan(app):

    logger.info("Starting CursorCode API")

    await init_db()

    yield

    logger.info("Closing database")

    await engine.dispose()

    logger.info("Database closed")


# ─────────────────────────────────────
# Utility
# ─────────────────────────────────────


def get_engine() -> AsyncEngine:

    return engine
