"""Section 1: Infrastructure Health
===================================
Test that MongoDB and Redis are reachable and responsive.
Run this FIRST to verify your infra is up before debugging anything else.

Prerequisites:
    just up    # starts MongoDB (port 27018) + Redis (port 6379)

Usage:
    python -m testscripts.debug-01-infra-health
    # or from project root:
    python testscripts/debug-01-infra-health.py
"""

import asyncio
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings
from src.persistence.mongodb import Database
from src.persistence.redis import Cache


async def main() -> None:
    settings = get_settings()

    print("=" * 50)
    print("Section 1: Infrastructure Health")
    print("=" * 50)

    # --- 1a: MongoDB ---
    print("\n[1a] Testing MongoDB connection...")
    print(f"     URL: {settings.mongodb_url}")
    print(f"     Database: {settings.mongodb_database}")

    db = Database()
    try:
        await db.connect(settings)
        # Ping to verify
        result = await db._client.admin.command("ping")
        print(f"     Ping: {result}")

        # List collections
        collections = await db._db.list_collection_names()
        print(f"     Collections: {collections}")

        # Count documents in each collection
        for coll_name in sorted(collections):
            count = await db._db[coll_name].count_documents({})
            print(f"       - {coll_name}: {count} docs")

        print("     [OK] MongoDB connected")
    except Exception as e:
        print(f"     [FAIL] MongoDB: {e}")
    finally:
        await db.disconnect()

    # --- 1b: Redis ---
    print("\n[1b] Testing Redis connection...")
    print(f"     URL: {settings.redis_url}")

    cache = Cache()
    try:
        await cache.connect(settings)
        # Ping
        pong = await cache._redis.ping()
        print(f"     Ping: {pong}")

        # Check info
        info = await cache._redis.info("server")
        print(f"     Redis version: {info.get('redis_version', '?')}")

        # Count keys
        db_size = await cache._redis.dbsize()
        print(f"     Total keys: {db_size}")

        print("     [OK] Redis connected")
    except Exception as e:
        print(f"     [FAIL] Redis: {e}")
    finally:
        await cache.disconnect()

    print("\n" + "=" * 50)
    print("Infrastructure health check complete.")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
