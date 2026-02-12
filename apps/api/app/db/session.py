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
    echo_pool="debug" if settings.ENVIRONMENT == "development" else False,
    future=True,
    # Pooling tuned for Supabase + serverless platforms
    pool_pre_ping=True,           # Detect & replace broken/stale connections
    pool_size=5,                  # Conservative for Supabase free tier (\~15–20 concurrent max)
    max_overflow=5,               # Allow bursts during spikes
    pool_timeout=30,              # Wait time to acquire connection
    pool_recycle=600,             # Recycle every 10 min (helps with Supabase idle timeouts)
    connect_args={
        # Supabase requires SSL; modern way (more explicit than just ssl=True)
        "ssl": {"sslmode": "require"} if "supabase" in str(settings.DATABASE_URL).lower() else None,
        "connect_timeout": 15,    # Fail fast on bad connections
    },
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
# Startup: Test connection + optional Redis ping
# ────────────────────────────────────────────────
async def init_db():
    """
    Run on app startup – verifies connection to PostgreSQL/Supabase.
    Logs success or raises critical error.
    Optional: pings Redis if configured.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.commit()

        db_type = "Supabase (pooled)" if "supabase" in str(settings.DATABASE_URL).lower() else "PostgreSQL"
        logger.info(
            f"{db_type} connection verified successfully",
            extra={"database_url": str(settings.DATABASE_URL)}
        )

        # Optional Redis check (used for rate limiting, Celery, caching)
        if settings.REDIS_URL:
            try:
                from redis.asyncio import Redis
                redis = Redis.from_url(str(settings.REDIS_URL))
                await redis.ping()
                await redis.aclose()
                logger.info("Redis connection verified", extra={"redis_url": str(settings.REDIS_URL)})
            except Exception as redis_exc:
                logger.warning("Redis ping failed (continuing without)", exc_info=redis_exc)

    except Exception as e:
        logger.critical(
            "Database connection failed on startup",
            exc_info=True,
            extra={"database_url": str(settings.DATABASE_URL)}
        )
        raise RuntimeError("Database unavailable") from e
    finally:
        # Ensure any temp resources are cleaned (rare but safe)
        pass


# ────────────────────────────────────────────────
# Lifespan context manager (use in main.py)
# ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    """
    FastAPI lifespan handler – initialize & clean up database connections.
    """
    await init_db()  # Test connection + Redis on startup

    yield  # App runs here

    # Graceful shutdown – close all pooled connections
    try:
        await engine.dispose()
        logger.info("Database engine disposed on shutdown")
    except Exception as dispose_exc:
        logger.warning("Error during DB shutdown", exc_info=dispose_exc)


# ────────────────────────────────────────────────
# Utility: Get raw engine (for Alembic migrations, CLI tools, tests)
# ────────────────────────────────────────────────
def get_engine() -> AsyncEngine:
    return engine
