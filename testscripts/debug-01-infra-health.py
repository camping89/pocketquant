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
    # connect() calls server_info() internally — if it passes, MongoDB is healthy
    print("\n[1a] Testing MongoDB connection...")
    print(f"     URL: {settings.mongodb_url}")
    print(f"     Database: {settings.mongodb_database}")

    db = Database()
    try:
        await db.connect(settings)

        # List collections via public API
        database = db.get_database()
        collections = await database.list_collection_names()
        print(f"     Collections: {collections}")

        for coll_name in sorted(collections):
            count = await db.get_collection(coll_name).count_documents({})
            print(f"       - {coll_name}: {count} docs")

        print("     [OK] MongoDB connected")
    except Exception as e:
        print(f"     [FAIL] MongoDB: {e}")
    finally:
        await db.disconnect()

    # --- 1b: Redis ---
    # connect() calls ping() internally — if it passes, Redis is healthy
    print("\n[1b] Testing Redis connection...")
    print(f"     URL: {settings.redis_url}")

    cache = Cache()
    try:
        await cache.connect(settings)
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
