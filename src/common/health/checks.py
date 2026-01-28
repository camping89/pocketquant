"""Health check functions for infrastructure dependencies."""

import time

from src.infrastructure.persistence import Cache, Database


async def check_database() -> dict:
    """Check MongoDB connectivity and measure latency."""
    start = time.time()
    db = Database.get_database()
    await db.command("ping")
    return {"latency_ms": int((time.time() - start) * 1000)}


async def check_redis() -> dict:
    """Check Redis connectivity and measure latency."""
    start = time.time()
    client = Cache._get_client()
    await client.ping()
    return {"latency_ms": int((time.time() - start) * 1000)}
