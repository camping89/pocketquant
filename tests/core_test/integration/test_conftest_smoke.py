"""Smoke test verifying conftest testcontainers wire correctly.

Marked `integration` because it requires Docker. Skipped by `pytest -m "not integration"`.
Delete this file once integration tests using `settings` exist organically.
"""

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_settings_not_prod(settings):
    assert "207.148.79.60" not in str(settings.mongodb_url)
    assert "207.148.79.60" not in str(settings.redis_url)
    assert settings.mongodb_database == "pocketquant_test"


@pytest.mark.asyncio
async def test_mongo_container_reachable(settings):
    from pymongo.asynchronous.mongo_client import AsyncMongoClient

    client = AsyncMongoClient(str(settings.mongodb_url), serverSelectionTimeoutMS=5000)
    info = await client.server_info()
    await client.close()
    assert info.get("version", "").startswith("7.")


@pytest.mark.asyncio
async def test_redis_container_reachable(settings):
    import redis.asyncio as redis

    client = redis.from_url(str(settings.redis_url), socket_timeout=5)
    # redis-py stubs type ping() as sync bool; the asyncio client returns a coroutine
    pong = await client.ping()  # pyright: ignore[reportGeneralTypeIssues]
    await client.aclose()
    assert pong is True
