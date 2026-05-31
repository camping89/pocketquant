"""Pytest configuration for pocketquant-api tests.

Mirrors the session fixture bootstrap from pocketquant-core so integration
tests in this package work both standalone and in the full workspace suite.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pocketquant.core.config import Settings
from testcontainers.mongodb import MongoDbContainer
from testcontainers.redis import RedisContainer

_PROD_HOST_FRAGMENT = "207.148.79.60"


# Placeholder values for the bare ``Settings()`` path (e.g. the structlog
# ``add_app_context`` processor calls ``get_settings()`` at log time). They keep
# the suite hermetic: tests must run with no project ``.env`` present (CI) just
# as well as with one (local/direnv). Fixtures that need real infra build their
# own ``Settings`` against ephemeral containers and ignore these.
_TEST_ENV_DEFAULTS = {
    "APP_NAME": "pocketquant-test",
    "APP_VERSION": "0.0.0",
    "ENVIRONMENT": "development",
    "MONGODB_URL": "mongodb://localhost:27017/pocketquant_test",
    "MONGODB_DATABASE": "pocketquant_test",
    "MONGODB_MIN_POOL_SIZE": "1",
    "MONGODB_MAX_POOL_SIZE": "10",
    "REDIS_URL": "redis://localhost:6379/1",
    "REDIS_CACHE_TTL": "3600",
    "LOG_LEVEL": "DEBUG",
    "LOG_FORMAT": "console",
}


def pytest_configure(config: pytest.Config) -> None:
    import os

    for var in ("MONGODB_URL", "REDIS_URL"):
        value = os.environ.get(var, "")
        if _PROD_HOST_FRAGMENT in value:
            raise RuntimeError(
                f"Refusing to run tests: {var} points at production "
                f"({_PROD_HOST_FRAGMENT}). Unset the env var or use a local URL."
            )

    # Seed required Settings fields only when absent, so a real dev environment
    # (direnv/.env) keeps precedence and the prod-guard above still sees real URLs.
    for key, val in _TEST_ENV_DEFAULTS.items():
        os.environ.setdefault(key, val)


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
    """Test Settings wired to ephemeral containers."""
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
