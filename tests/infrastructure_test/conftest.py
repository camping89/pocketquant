"""Pytest fixtures for pocketquant-infrastructure tests.

Tests run against ephemeral docker containers (testcontainers) so they never
touch the production VPS database. Session fixtures spin up Mongo + Redis once
per pytest run. Local Docker is required.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from pocketquant.core.config import Settings
from pocketquant.infrastructure.persistence.mongodb import Database
from pocketquant.infrastructure.persistence.redis import Cache
from testcontainers.mongodb import MongoDbContainer
from testcontainers.redis import RedisContainer

# Block tests against any production DB even if a stray env var leaks through.
_PROD_HOST_FRAGMENT = "207.148.79.60"


def pytest_configure(config: pytest.Config) -> None:
    for var in ("MONGODB_URL", "REDIS_URL"):
        value = os.environ.get(var, "")
        if _PROD_HOST_FRAGMENT in value:
            raise RuntimeError(
                f"Refusing to run tests: {var} points at production "
                f"({_PROD_HOST_FRAGMENT}). Unset the env var or use a local URL."
            )


@pytest.fixture(scope="session")
def mongo_container() -> Iterator[MongoDbContainer]:
    with MongoDbContainer("mongo:7.0") as mongo:
        yield mongo


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7.2-alpine") as redis:
        yield redis


@pytest.fixture
def settings(
    mongo_container: MongoDbContainer,
    redis_container: RedisContainer,
) -> Settings:
    """Test Settings wired to ephemeral containers. Never reads any .env file."""
    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)

    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        app_name="pocketquant-test",
        app_version="0.0.1",
        environment="development",
        mongodb_url=mongo_container.get_connection_url(),
        mongodb_database="pocketquant_test",
        mongodb_min_pool_size=1,
        mongodb_max_pool_size=10,
        redis_url=f"redis://{redis_host}:{redis_port}/1",
        redis_cache_ttl=3600,
        log_level="DEBUG",
        log_format="console",
        enable_jobs=False,
    )


@pytest.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    """Per-test Mongo Database connected to the testcontainer.

    Drops the backtest collections on teardown so they don't leak between tests.
    """
    db = Database()
    await db.connect(settings)
    try:
        yield db
    finally:
        for coll in (
            "backtest_runs",
            "backtest_orders",
            "backtest_trades",
            "backtest_optimization_runs",
        ):
            try:
                await db.get_collection(coll).drop()
            except Exception:  # noqa: BLE001
                pass
        await db.disconnect()


@pytest.fixture
async def cache(settings: Settings) -> AsyncIterator[Cache]:
    """Per-test Redis Cache connected to the testcontainer."""
    c = Cache()
    await c.connect(settings)
    try:
        yield c
    finally:
        await c.disconnect()
