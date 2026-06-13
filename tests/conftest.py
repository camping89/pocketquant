"""Root conftest for tests/ — sys.path bootstrap, prod-DB guard, env seeding.

Single source for the test-environment contract; per-suite conftests only add
fixtures (testcontainers, Settings, app objects) on top.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from testcontainers.mongodb import MongoDbContainer
from testcontainers.redis import RedisContainer

# Workspace root = parent of this file's directory (tests/). Inserted so the
# `scripts` package (scripts/audit_bar_quality.py, ...) is importable as
# `scripts.<module>` in tests. pytest's pythonpath=["."] in pyproject.toml is
# supposed to handle this, but requires the insertion to happen before package
# collection when running from outside the workspace root.
_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

# Block tests against any production DB even if a stray env var leaks through.
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


# Session-scoped containers — started once per pytest run for the whole tree.
# Session fixtures are keyed by defining module path, so defining them here (the
# root conftest, visible to every suite via fixture inheritance) means ONE Mongo
# + ONE Redis for the entire run instead of one pair per suite conftest. Per-test
# isolation comes from fresh DB names + teardown drops, not from container count.
@pytest.fixture(scope="session")
def mongo_container() -> Iterator[MongoDbContainer]:
    with MongoDbContainer("mongo:7.0") as mongo:
        yield mongo


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7.2-alpine") as redis:
        yield redis
