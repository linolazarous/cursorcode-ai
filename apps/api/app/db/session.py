"""
Database session management for CursorCode AI.
Async SQLAlchemy engine, session factory, and FastAPI dependency.
Production-ready: connection pooling, transaction handling, async support.
Supabase-ready: pooled connection (port 6543), SSL forced via connect_args.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# Global Async Engine (singleton – created once)
# ────────────────────────────────────────────────
engine: AsyncEngine = create_async_engine(
    str(settings.DATABASE_URL),
    echo=settings.ENVIRONMENT == "development",
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=600,
    connect_args={
        "ssl": {
            "sslmode": "require",          # Supabase enforces SSL
            "check_hostname": False,       # Pooler hostname may not match cert
            "verify_cert": False,          # Critical: disables cert chain verification (self-signed in Supabase pooler)
        },
        "server_settings": {"application_name": "cursorcode-api"},
    },
)

# Async Session Factory
async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


# ────────────────────────────────────────────────
# FastAPI Dependency
# ────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
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
# Startup: Test connection (non-fatal)
# ────────────────────────────────────────────────
async def init_db():
    """
    Run on app startup – verifies connection to PostgreSQL/Supabase.
    Logs detailed error but does NOT crash app (allows partial startup).
    """
    db_url = str(settings.DATABASE_URL)
    logger.info("Testing database connection", extra={"url": db_url})

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            logger.info(
                "Database connection successful",
                extra={
                    "url": db_url,
                    "first_result": result.scalar(),
                }
            )
    except Exception as e:
        logger.critical(
            "Database connection failed on startup",
            exc_info=True,
            extra={
                "url": db_url,
                "error_type": type(e).__name__,
                "error_msg": str(e),
            }
        )
        # Do NOT raise here – allow app to start (DB routes will 500)


# ────────────────────────────────────────────────
# Lifespan (use in main.py)
# ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    await init_db()  # Test DB on startup (non-fatal)
    yield
    await engine.dispose()
    logger.info("Database engine disposed on shutdown")


# Utility for migrations/CLI
def get_engine() -> AsyncEngine:
    return engine
