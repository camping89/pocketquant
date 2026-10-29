"""Settings for the market-data infra tests.

A ``Settings`` built with ``_env_file=None`` gives the real type without
reading the developer's ``.env``.
"""

from __future__ import annotations

from pocketquant.core.config import Settings


def build_settings() -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        app_name="pocketquant-test",
        app_version="0.0.1",
        environment="development",
        mongodb_url="mongodb://localhost:27017",
        mongodb_database="pocketquant_test",
        mongodb_min_pool_size=1,
        mongodb_max_pool_size=10,
        redis_url="redis://localhost:6379/1",
        redis_cache_ttl=3600,
        log_level="DEBUG",
        log_format="console",
        app_roles="api",
    )
