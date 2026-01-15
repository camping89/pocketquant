"""Redis cache implementation for global caching."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import redis.asyncio as redis

from src.common.logging import get_logger
from src.config import Settings

logger = get_logger(__name__)


class Cache:
    """Redis cache manager for global application caching."""

    _client: redis.Redis | None = None
    _default_ttl: int = 3600

    @classmethod
    async def connect(cls, settings: Settings) -> None:
        """Establish Redis connection.

        Args:
            settings: Application settings with Redis configuration.
        """
        logger.info("connecting_to_redis")

        cls._client = redis.from_url(
            str(settings.redis_url),
            encoding="utf-8",
            decode_responses=True,
        )
        cls._default_ttl = settings.redis_cache_ttl
        await cls._client.ping()
        logger.info("redis_connected")

    @classmethod
    async def disconnect(cls) -> None:
        """Close Redis connection."""
        if cls._client is not None:
            await cls._client.close()
            cls._client = None
            logger.info("redis_disconnected")

    @classmethod
    def _get_client(cls) -> redis.Redis:
        """Get the Redis client.

        Returns:
            The Redis client instance.

        Raises:
            RuntimeError: If cache is not connected.
        """
        if cls._client is None:
            raise RuntimeError("Cache not connected. Call Cache.connect() first.")
        return cls._client

    @classmethod
    async def get(cls, key: str) -> Any | None:
        """Get a value from cache.

        Args:
            key: Cache key.

        Returns:
            The cached value or None if not found.
        """
        client = cls._get_client()
        value = await client.get(key)

        if value is None:
            logger.debug("cache_miss", key=key)
            return None

        logger.debug("cache_hit", key=key)
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    @classmethod
    async def set(
        cls,
        key: str,
        value: Any,
        ttl: int | timedelta | None = None,
    ) -> None:
        """Set a value in cache.

        Args:
            key: Cache key.
            value: Value to cache (will be JSON serialized if not a string).
            ttl: Time-to-live in seconds or as timedelta. Uses default if not specified.
        """
        client = cls._get_client()

        if ttl is None:
            ttl = cls._default_ttl
        elif isinstance(ttl, timedelta):
            ttl = int(ttl.total_seconds())

        if isinstance(value, str):
            serialized = value
        else:
            serialized = json.dumps(value, default=str)

        await client.set(key, serialized, ex=ttl)
        logger.debug("cache_set", key=key, ttl=ttl)

    @classmethod
    async def delete(cls, key: str) -> bool:
        """Delete a key from cache.

        Args:
            key: Cache key to delete.

        Returns:
            True if key was deleted, False if key didn't exist.
        """
        client = cls._get_client()
        result = await client.delete(key)
        logger.debug("cache_delete", key=key, deleted=bool(result))
        return bool(result)

    @classmethod
    async def delete_pattern(cls, pattern: str) -> int:
        """Delete all keys matching a pattern.

        Args:
            pattern: Pattern to match (e.g., "market_data:*").

        Returns:
            Number of keys deleted.
        """
        client = cls._get_client()
        keys = []

        async for key in client.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            deleted = await client.delete(*keys)
            logger.debug("cache_delete_pattern", pattern=pattern, deleted=deleted)
            return deleted

        return 0

    @classmethod
    async def exists(cls, key: str) -> bool:
        """Check if a key exists in cache.

        Args:
            key: Cache key.

        Returns:
            True if key exists, False otherwise.
        """
        client = cls._get_client()
        return bool(await client.exists(key))

    @classmethod
    async def get_or_set(
        cls,
        key: str,
        factory: callable,
        ttl: int | timedelta | None = None,
    ) -> Any:
        """Get value from cache or compute and cache it.

        Args:
            key: Cache key.
            factory: Async callable that produces the value if not cached.
            ttl: Time-to-live for the cached value.

        Returns:
            The cached or computed value.
        """
        value = await cls.get(key)
        if value is not None:
            return value

        value = await factory()
        await cls.set(key, value, ttl)
        return value


@asynccontextmanager
async def get_cache(settings: Settings) -> AsyncGenerator[type[Cache]]:
    """Context manager for cache connection.

    Args:
        settings: Application settings.

    Yields:
        The Cache class with active connection.
    """
    try:
        await Cache.connect(settings)
        yield Cache
    finally:
        await Cache.disconnect()
