"""Health check functions for infrastructure dependencies."""

import time

from pocketquant.infrastructure.persistence.mongodb import Database
from pocketquant.infrastructure.persistence.redis import Cache


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
    await client.ping()
    return {"latency_ms": int((time.time() - start) * 1000)}
