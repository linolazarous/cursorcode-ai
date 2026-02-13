"""
app/core/redis.py
Centralized Redis client & utilities for CursorCode AI API.
Handles connection pooling, async context management, health checks, and common patterns.
Production-ready (2026): connection retry, logging, monitoring, graceful shutdown.
"""

import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, AsyncGenerator, Optional  # ← FIXED: added missing imports

from redis.asyncio import Redis, ConnectionPool, RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# Global connection pool (shared across the app)
# ────────────────────────────────────────────────
_redis_pool: Optional[ConnectionPool] = None


def get_redis_pool() -> ConnectionPool:
    """
    Lazy-initialize and return a shared Redis connection pool.
    Uses settings.REDIS_URL (supports redis://, rediss://, unix://)
    """
    global _redis_pool
    if _redis_pool is None:
        try:
            _redis_pool = ConnectionPool.from_url(
                str(settings.REDIS_URL),
                max_connections=20,           # adjust based on traffic
                decode_responses=False,       # we decode manually when needed
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            logger.info("Redis connection pool initialized")
        except Exception as e:
            logger.critical(f"Failed to initialize Redis pool: {e}", exc_info=True)
            raise RuntimeError("Redis initialization failed") from e

    return _redis_pool


@asynccontextmanager
async def get_redis_client() -> AsyncGenerator[Redis, None]:
    """
    Async context manager for acquiring a Redis client from the pool.
    Usage:
        async with get_redis_client() as redis:
            await redis.set(...)
    """
    pool = get_redis_pool()
    client = Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.close()  # returns connection to pool, does not disconnect


# ────────────────────────────────────────────────
# Health check & monitoring
# ────────────────────────────────────────────────
async def check_redis_health() -> bool:
    """
    Simple ping-based health check.
    Returns True if Redis is responsive.
    """
    try:
        async with get_redis_client() as redis:
            return await redis.ping()
    except RedisError as e:
        logger.error(f"Redis health check failed: {e}")
        return False


async def get_redis_info() -> Dict[str, Any]:
    """
    Get basic Redis server info (useful for /health or monitoring endpoints).
    """
    try:
        async with get_redis_client() as redis:
            info = await redis.info()
            return {
                "status": "healthy",
                "used_memory_human": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "uptime_in_days": info.get("uptime_in_days"),
            }
    except RedisError as e:
        logger.error(f"Redis info fetch failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


# ────────────────────────────────────────────────
# Common utility functions
# ────────────────────────────────────────────────
async def set_with_ttl(
    key: str,
    value: Any,
    ttl_seconds: int,
    redis: Optional[Redis] = None,
) -> bool:
    """
    Set key with expiration. Accepts existing redis client or creates one.
    """
    if redis is None:
        async with get_redis_client() as r:
            return await set_with_ttl(key, value, ttl_seconds, r)

    try:
        await redis.set(key, value, ex=ttl_seconds)
        return True
    except RedisError as e:
        logger.error(f"Redis set failed for key {key}: {e}")
        return False


async def get_or_set_default(
    key: str,
    default_value: Any,
    ttl_seconds: int,
    redis: Optional[Redis] = None,
) -> Any:
    """
    Get value or set default and return it.
    """
    if redis is None:
        async with get_redis_client() as r:
            return await get_or_set_default(key, default_value, ttl_seconds, r)

    value = await redis.get(key)
    if value is None:
        await redis.set(key, default_value, ex=ttl_seconds)
        return default_value
    return value


# ────────────────────────────────────────────────
# Graceful shutdown (call on app shutdown)
# ────────────────────────────────────────────────
async def close_redis_pool():
    """Close shared Redis connection pool on application shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
        logger.info("Redis connection pool closed")
