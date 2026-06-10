"""Health check functions for infrastructure dependencies."""

import time

from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.redis import Cache


async def check_database(database: Database) -> dict:
    """Check MongoDB connectivity and measure latency."""
    start = time.time()
    db = database.get_database()
    await db.command("ping")
    return {"latency_ms": int((time.time() - start) * 1000)}


async def check_redis(cache: Cache) -> dict:
    """Check Redis connectivity and measure latency."""
    start = time.time()
    client = cache.get_client()
    # redis-py types ping() as sync bool, but redis.asyncio returns an awaitable.
    await client.ping()  # pyright: ignore[reportGeneralTypeIssues]
    return {"latency_ms": int((time.time() - start) * 1000)}
