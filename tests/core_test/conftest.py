"""Pytest configuration and fixtures.

Tests run against ephemeral docker containers (testcontainers) so they never
touch the production VPS database. The session-scoped Mongo + Redis containers
live in the root ``tests/conftest.py`` and resolve here via fixture inheritance.

Local Docker is required.
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator, Callable, Iterator
from zoneinfo import ZoneInfoNotFoundError

import pytest
import tzlocal
from testcontainers.mongodb import MongoDbContainer
from testcontainers.redis import RedisContainer

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.redis import Cache


@pytest.fixture
def host_timezone() -> Iterator[Callable[..., None]]:
    """Switch the process timezone for one test, restoring it on teardown.

    ``time.tzset`` only refreshes the C library, while ``tzlocal`` memoizes the
    zone separately, so a caller that changes only one of them observes a stale
    zone and silently proves nothing.

    Pass canonical IANA names. Deprecated aliases (``Asia/Saigon``, ``US/Central``)
    live in the separate ``tzdata-legacy`` package on Debian/Ubuntu, and glibc
    falls back to UTC for a zone it cannot find rather than raising — hence the
    resolve check. Set ``require_resolved=False`` to exercise that degradation
    deliberately.
    """
    original = os.environ.get("TZ")

    def refresh_caches() -> None:
        time.tzset()
        try:
            tzlocal.reload_localzone()
        except ZoneInfoNotFoundError:
            # An unresolvable zone makes tzlocal's cache refresh raise, even
            # though get_localzone_name() still returns the alias string. Drop
            # what we can and let the test observe the degraded state.
            pass

    def apply(zone: str, *, require_resolved: bool = True) -> None:
        os.environ["TZ"] = zone
        refresh_caches()
        if require_resolved and zone != "UTC":
            assert time.timezone != 0, f"{zone} did not resolve; it fell back to UTC"

    try:
        yield apply
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        refresh_caches()


# Per-test settings — fresh DB names so tests don't bleed state.
# Container reuse keeps startup cost paid once.
@pytest.fixture
def settings(
    mongo_container: MongoDbContainer,
    redis_container: RedisContainer,
) -> Settings:
    """Test Settings wired to ephemeral containers. Never reads any .env file."""
    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)

    return Settings(
        _env_file=None,  # disable .env loading  # pyright: ignore[reportCallIssue]
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
def event_bus() -> EventBus:
    return EventBus()


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
