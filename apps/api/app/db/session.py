# apps/api/app/db/session.py
"""
Database session management for CursorCode AI.
Async SQLAlchemy engine, session factory, and FastAPI dependency.
Production-ready: connection pooling, transaction handling, async support.
Supabase-ready: uses pooled connection (recommended for Render/Fly/Railway).
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

from app.core.config import settings

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# Global Async Engine (singleton – created once)
# ────────────────────────────────────────────────
engine: AsyncEngine = create_async_engine(
    str(settings.DATABASE_URL),
    echo=settings.ENVIRONMENT == "development",  # SQL logging only in dev
    future=True,
    # Pooling tuned for Supabase + serverless platforms (Render/Fly/Railway)
    pool_pre_ping=True,           # Detect & replace broken/stale connections
    pool_size=10,                 # Base pool size (Supabase free tier \~15–20 concurrent ok)
    max_overflow=5,               # Allow bursts during spikes
    pool_timeout=30,              # Wait time to acquire connection
    pool_recycle=600,             # Recycle every 10 min (helps with Supabase idle timeouts)
    connect_args={
        "ssl": True,              # Supabase requires SSL
        "connect_timeout": 15,    # Fail fast on bad connections
    } if "supabase" in str(settings.DATABASE_URL).lower() else {},
)


# ────────────────────────────────────────────────
# Async Session Factory (per-request sessions)
# ────────────────────────────────────────────────
async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,       # Prevent expired objects after commit
    class_=AsyncSession,
)


# ────────────────────────────────────────────────
# FastAPI Dependency: per-request async session
# ────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: yields a new async session per request.
    Automatically commits on success, rolls back on error, closes always.
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
# Startup: Test connection (called from lifespan)
# ────────────────────────────────────────────────
async def init_db():
    """
    Run on app startup – verifies connection to Supabase/PostgreSQL.
    Logs success or raises critical error.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.commit()

        db_type = "Supabase (pooled)" if "supabase" in str(settings.DATABASE_URL).lower() else "PostgreSQL"
        logger.info(f"{db_type} connection verified successfully")

        # Optional: test Redis if used for Celery/rate limiting
        # from redis.asyncio import Redis
        # redis = Redis.from_url(settings.REDIS_URL)
        # await redis.ping()
        # logger.info("Redis connection verified")

    except Exception as e:
        logger.critical("Database connection failed on startup", exc_info=True)
        raise RuntimeError("Database unavailable") from e


# ────────────────────────────────────────────────
# Lifespan context manager (use in main.py)
# ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    """
    FastAPI lifespan handler – initialize & clean up database connections.
    """
    await init_db()  # Test connection on startup

    yield  # App runs here

    # Graceful shutdown – close all pooled connections
    try:
        await engine.dispose()
        logger.info("Database engine disposed on shutdown")
    except Exception as e:
        logger.warning(f"Error during DB shutdown: {e}")


# ────────────────────────────────────────────────
# Utility: Get raw engine (for Alembic migrations, CLI tools, tests)
# ────────────────────────────────────────────────
def get_engine() -> AsyncEngine:
    return engine
