import json
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import redis.asyncio as redis

from src.common.logging import get_logger
from src.config import Settings

logger = get_logger(__name__)


class Cache:
    _client: redis.Redis | None = None
    _default_ttl: int = 3600

    @classmethod
    async def connect(cls, settings: Settings) -> None:
        logger.info("redis.connecting")

        cls._client = redis.from_url(
            str(settings.redis_url),
            encoding="utf-8",
            decode_responses=True,
        )
        cls._default_ttl = settings.redis_cache_ttl
        await cls._client.ping()
        logger.info("redis.connected")

    @classmethod
    async def disconnect(cls) -> None:
        if cls._client is not None:
            await cls._client.close()
            cls._client = None
            logger.info("redis.disconnected")

    @classmethod
    def _get_client(cls) -> redis.Redis:
        if cls._client is None:
            raise RuntimeError("Cache not connected. Call Cache.connect() first.")
        return cls._client

    @classmethod
    async def get(cls, key: str) -> Any | None:
        client = cls._get_client()
        value = await client.get(key)

        if value is None:
            logger.debug("redis.cache_miss", key=key)
            return None

        logger.debug("redis.cache_hit", key=key)
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
        logger.debug("redis.cache_set", key=key, ttl_seconds=ttl)

    @classmethod
    async def delete(cls, key: str) -> bool:
        client = cls._get_client()
        result = await client.delete(key)
        logger.debug("redis.cache_deleted", key=key, was_present=bool(result))
        return bool(result)

    @classmethod
    async def delete_pattern(cls, pattern: str) -> int:
        client = cls._get_client()
        keys = []

        async for key in client.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            deleted = await client.delete(*keys)
            logger.debug("redis.cache_pattern_deleted", pattern=pattern, keys_deleted=deleted)
            return deleted

        return 0

    @classmethod
    async def exists(cls, key: str) -> bool:
        client = cls._get_client()
        return bool(await client.exists(key))

    @classmethod
    async def get_or_set(
        cls,
        key: str,
        factory: Callable,
        ttl: int | timedelta | None = None,
    ) -> Any:
        value = await cls.get(key)
        if value is not None:
            return value

        value = await factory()
        await cls.set(key, value, ttl)
        return value


@asynccontextmanager
async def get_cache(settings: Settings) -> AsyncGenerator[type[Cache]]:
    try:
        await Cache.connect(settings)
        yield Cache
    finally:
        await Cache.disconnect()
