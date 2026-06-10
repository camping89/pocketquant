"""Pytest configuration for baseline regression tests.

Seeds the env vars required by bare ``Settings()`` so app/bff modules can be
imported and FastAPI app objects constructed fully offline (no Mongo/Redis).
Duplicate of the per-package conftest seeding until the restructure
consolidates env seeding into the root ``tests/conftest.py``.
"""

from __future__ import annotations

import pytest

_PROD_HOST_FRAGMENT = "207.148.79.60"

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

    for key, val in _TEST_ENV_DEFAULTS.items():
        os.environ.setdefault(key, val)

    # Schema-affecting vars must be FORCED, not defaulted: app_version flows into
    # FastAPI(version=...) → openapi()["info"]["version"]. A direnv/.env shell
    # exporting APP_VERSION would otherwise produce spurious snapshot drift.
    os.environ["APP_NAME"] = _TEST_ENV_DEFAULTS["APP_NAME"]
    os.environ["APP_VERSION"] = _TEST_ENV_DEFAULTS["APP_VERSION"]
