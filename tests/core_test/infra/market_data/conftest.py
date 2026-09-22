"""Settings and symbol fakes for the routing adapters.

The routing adapters are pure dispatch over injected children, so these tests
need no container: a ``Settings`` built with ``_env_file=None`` gives the real
type without reading the developer's ``.env``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.config import Settings
from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.domain.symbol import Symbol


def build_settings(
    providers: dict[AssetClass, list[str]],
    overrides: dict[str, list[str]] | None = None,
) -> Settings:
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
        enable_jobs=False,
        market_data_providers=providers,
        symbol_provider_overrides=overrides or {},
    )


def lookup_returning(asset_class: AssetClass | None) -> MagicMock:
    """A ``SymbolLookupHelper`` stub; ``None`` means the symbol is unseeded."""
    helper = MagicMock()
    symbol = (
        None
        if asset_class is None
        else Symbol.create(symbol="ES1!:CME_MINI", asset_class=asset_class)
    )
    helper.get = AsyncMock(return_value=symbol)
    return helper


@pytest.fixture
def futures_lookup() -> MagicMock:
    return lookup_returning(AssetClass.INDEX_FUTURE)
