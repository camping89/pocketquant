"""Redis cache manager — instance-based for DI container."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import redis.asyncio as redis

from src.common.logging import get_logger
from src.config import Settings

logger = get_logger(__name__)


class Cache:
    """Redis cache manager. Instance-based, managed by DI container."""

    def __init__(self) -> None:
        self._client: redis.Redis | None = None
        self._default_ttl: int = 3600

    async def connect(self, settings: Settings) -> None:
        logger.info("redis.connecting")

        self._client = redis.from_url(
            str(settings.redis_url),
            encoding="utf-8",
            decode_responses=True,
        )
        self._default_ttl = settings.redis_cache_ttl
        await self._client.ping()
        logger.info("redis.connected")

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("redis.disconnected")

    def get_client(self) -> redis.Redis:
        """Get Redis client, raising if not connected."""
        if self._client is None:
            raise RuntimeError("Cache not connected. Call Cache.connect() first.")
        return self._client

    async def get(self, key: str) -> Any | None:
        client = self.get_client()
        value = await client.get(key)

        if value is None:
            logger.debug("redis.cache_miss", key=key)
            return None

        logger.debug("redis.cache_hit", key=key)
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            logger.error("redis.cache_corrupted", key=key, error=str(e))
            raise ValueError(f"Corrupted cache data for key '{key}'") from e

    async def mget(self, keys: list[str]) -> list[Any]:
        """Get multiple values by keys. Returns list in same order (None for misses)."""
        if not keys or self._client is None:
            return [None] * len(keys)
        client = self.get_client()
        raw_values = await client.mget(keys)
        return [json.loads(v) if v else None for v in raw_values]

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | timedelta | None = None,
    ) -> None:
        client = self.get_client()

        if ttl is None:
            ttl = self._default_ttl
        elif isinstance(ttl, timedelta):
            ttl = int(ttl.total_seconds())

        if isinstance(value, str):
            serialized = value
        else:
            serialized = json.dumps(value, default=str)

        await client.set(key, serialized, ex=ttl)
        logger.debug("redis.cache_set", key=key, ttl_seconds=ttl)

    async def delete(self, key: str) -> bool:
        client = self.get_client()
        result = await client.delete(key)
        logger.debug("redis.cache_deleted", key=key, was_present=bool(result))
        return bool(result)

    async def delete_pattern(self, pattern: str) -> int:
        client = self.get_client()
        keys = []

        async for key in client.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            deleted = await client.delete(*keys)
            logger.debug("redis.cache_pattern_deleted", pattern=pattern, keys_deleted=deleted)
            return deleted

        return 0

    async def exists(self, key: str) -> bool:
        client = self.get_client()
        return bool(await client.exists(key))

    async def get_or_set(
        self,
        key: str,
        factory: Callable,
        ttl: int | timedelta | None = None,
    ) -> Any:
        value = await self.get(key)
        if value is not None:
            return value

        value = await factory()
        await self.set(key, value, ttl)
        return value
