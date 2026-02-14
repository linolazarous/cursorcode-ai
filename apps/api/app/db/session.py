# app/db/session.py (updated engine + init_db)

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
        "ssl": True if "supabase" in str(settings.DATABASE_URL).lower() else None,
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
# Startup: Test connection
# ────────────────────────────────────────────────
async def init_db():
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            await conn.commit()
            logger.info(
                "Database connection verified",
                extra={
                    "database_url": str(settings.DATABASE_URL),
                    "first_result": result.scalar(),
                }
            )
    except Exception as e:
        logger.critical(
            "Database connection failed on startup",
            exc_info=True,
            extra={"database_url": str(settings.DATABASE_URL)}
        )
        raise RuntimeError("Database unavailable") from e


# ────────────────────────────────────────────────
# Lifespan (use in main.py)
# ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    await init_db()  # Test DB on startup
    yield
    await engine.dispose()
    logger.info("Database engine disposed on shutdown")


# Utility for migrations/CLI
def get_engine() -> AsyncEngine:
    return engine
