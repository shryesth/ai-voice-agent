"""
Redis client setup with connection pooling.

Provides async Redis client for caching and Celery broker.
"""

from typing import Optional
import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class RedisClient:
    """Redis connection manager with connection pooling."""

    pool: Optional[ConnectionPool] = None
    client: Optional[Redis] = None

    @classmethod
    async def connect(cls) -> None:
        """
        Initialize Redis connection pool and client.

        Raises:
            Exception: If connection fails
        """
        try:
            logger.info(
                "Connecting to Redis",
                url=settings.redis_url.split("@")[-1],  # Hide credentials if any
            )

            # Create connection pool for reuse
            cls.pool = ConnectionPool.from_url(
                settings.redis_url,
                decode_responses=True,
                max_connections=10,
            )

            # Create Redis client from pool
            cls.client = Redis(connection_pool=cls.pool)

            # Test connection
            await cls.client.ping()

            logger.info("Redis connected successfully")

        except Exception as e:
            logger.error(
                "Failed to connect to Redis",
                error=str(e),
                url=settings.redis_url.split("@")[-1],
            )
            raise

    @classmethod
    async def close(cls) -> None:
        """Close Redis connection gracefully."""
        if cls.client:
            logger.info("Closing Redis connection")
            await cls.client.aclose()
            cls.client = None

        if cls.pool:
            await cls.pool.disconnect()
            cls.pool = None

        logger.info("Redis connection closed")

    @classmethod
    async def ping(cls) -> bool:
        """
        Ping Redis to check connection health.

        Returns:
            True if connection is healthy, False otherwise
        """
        if not cls.client:
            return False

        try:
            await cls.client.ping()
            return True
        except Exception as e:
            logger.warning("Redis ping failed", error=str(e))
            return False

    @classmethod
    async def get(cls, key: str) -> Optional[str]:
        """
        Get value from Redis by key.

        Args:
            key: Redis key

        Returns:
            Value if exists, None otherwise
        """
        if not cls.client:
            raise RuntimeError("Redis client not initialized")

        return await cls.client.get(key)

    @classmethod
    async def set(
        cls,
        key: str,
        value: str,
        ex: Optional[int] = None
    ) -> bool:
        """
        Set value in Redis with optional expiration.

        Args:
            key: Redis key
            value: Value to store
            ex: Expiration time in seconds (optional)

        Returns:
            True if successful
        """
        if not cls.client:
            raise RuntimeError("Redis client not initialized")

        return await cls.client.set(key, value, ex=ex)

    @classmethod
    async def delete(cls, key: str) -> int:
        """
        Delete key from Redis.

        Args:
            key: Redis key to delete

        Returns:
            Number of keys deleted
        """
        if not cls.client:
            raise RuntimeError("Redis client not initialized")

        return await cls.client.delete(key)

    @classmethod
    async def exists(cls, key: str) -> bool:
        """
        Check if key exists in Redis.

        Args:
            key: Redis key to check

        Returns:
            True if key exists
        """
        if not cls.client:
            raise RuntimeError("Redis client not initialized")

        return bool(await cls.client.exists(key))


# Global Redis client instance
redis_client = RedisClient()
