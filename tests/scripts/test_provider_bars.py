"""provider_bars: refuses beside live trading and reports an unrouted symbol."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    UnknownDataProviderError,
)
from scripts.backfill import provider_bars
from tests.core_test.infra.market_data.conftest import build_settings

ARGS = ["--symbol", "XAUUSD:MT5", "--interval", "1m", "--days", "1"]


def test_it_refuses_while_live_trading_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = build_settings().model_copy(update={"exness_live_trading": True})
    monkeypatch.setattr(provider_bars, "get_settings", lambda: settings)
    create = MagicMock()
    monkeypatch.setattr(provider_bars, "create_container", create)

    assert provider_bars.main(ARGS) == 3
    create.assert_not_called()


def test_a_symbol_without_a_provider_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_bars, "get_settings", build_settings)
    provider = MagicMock()
    provider.fetch_ohlcv = AsyncMock(side_effect=UnknownDataProviderError("mt5"))
    container = MagicMock()
    container.get = AsyncMock(return_value=provider)
    container.close = AsyncMock()
    monkeypatch.setattr(provider_bars, "create_container", lambda _settings: container)

    assert provider_bars.main(ARGS) == 2
    container.close.assert_awaited_once()


def test_the_rate_fraction_reaches_the_container_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_bars, "get_settings", build_settings)
    seen = []
    provider = MagicMock()
    provider.fetch_ohlcv = AsyncMock(return_value=[])
    container = MagicMock()
    container.get = AsyncMock(return_value=provider)
    container.close = AsyncMock()

    def create(settings):
        seen.append(settings.exness_rate_fraction)
        return container

    monkeypatch.setattr(provider_bars, "create_container", create)

    assert provider_bars.main([*ARGS, "--rate-fraction", "0.25", "--dry-run"]) == 1
    assert seen == [0.25]
