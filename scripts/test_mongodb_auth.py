"""Test MongoDB authentication with both sync and async clients."""

import sys


def test_sync_docker_port():
    """Test connection to Docker MongoDB on port 27018."""
    from pymongo import MongoClient

    print("Test 1: Docker MongoDB on port 27018 with auth...")
    try:
        client = MongoClient(
            "mongodb://pocketquant:pocketquant_dev@localhost:27018/pocketquant?authSource=admin",
            serverSelectionTimeoutMS=5000,
        )
        result = client.admin.command("ping")
        print(f"  SUCCESS: {result}")
        client.close()
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_async_docker_port():
    """Test async connection to Docker MongoDB on port 27018."""
    from pymongo.asynchronous.mongo_client import AsyncMongoClient

    print("\nTest 2: Docker MongoDB on port 27018 with async client...")
    try:
        client = AsyncMongoClient(
            "mongodb://pocketquant:pocketquant_dev@localhost:27018/pocketquant?authSource=admin",
            serverSelectionTimeoutMS=5000,
        )
        result = await client.admin.command("ping")
        print(f"  SUCCESS: {result}")
        await client.close()
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def test_sync_local_port():
    """Test connection to local MongoDB on port 27018 (if exists)."""
    from pymongo import MongoClient

    print("\nTest 3: Local MongoDB on port 27018 (if exists)...")
    try:
        client = MongoClient(
            "mongodb://localhost:27018/pocketquant",
            serverSelectionTimeoutMS=2000,
        )
        result = client.admin.command("ping")
        print(f"  SUCCESS: {result}")
        print("  WARNING: Local MongoDB found on port 27018!")
        client.close()
        return True
    except Exception as e:
        print(f"  Not available (expected): {type(e).__name__}")
        return False


def main():
    import asyncio

    print("=" * 60)
    print("MongoDB Authentication Test (Port 27018)")
    print("=" * 60)
    print(f"Python version: {sys.version}")

    import pymongo

    print(f"PyMongo version: {pymongo.version}")
    print("=" * 60)

    test_sync_docker_port()
    asyncio.run(test_async_docker_port())
    test_sync_local_port()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
