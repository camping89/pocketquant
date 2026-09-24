"""The ``market_data_providers`` health check: routing and session state, no network."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.infra.market_data.provider_health_check import check_market_data_providers
from pocketquant.core.infra.market_data.symbol_provider_resolver import SymbolProviderResolver
from tests.core_test.infra.market_data.conftest import build_settings, lookup_returning

FUTURES = "ES1!:CME_MINI"
MAP = {
    AssetClass.CRYPTO_SPOT: ["binance"],
    AssetClass.INDEX_FUTURE: ["tradingview"],
}


def _tracked(*symbols: str) -> MagicMock:
    repo = MagicMock()
    repo.list_all = AsyncMock(return_value=[MagicMock(symbol=s) for s in symbols])
    return repo


def _calendars() -> MagicMock:
    factory = MagicMock()
    factory.for_symbol = AsyncMock(return_value=Continuous24x7Calendar())
    return factory


async def _check(tradingview_authenticated: bool, *symbols: str, credentialed: bool = True) -> dict:
    resolver = SymbolProviderResolver(
        settings=build_settings(MAP), symbol_lookup=lookup_returning(AssetClass.INDEX_FUTURE)
    )
    return await check_market_data_providers(
        {"binance": lambda: True, "tradingview": lambda: tradingview_authenticated},
        {"tradingview"} if credentialed else set(),
        resolver,
        _calendars(),
        _tracked(*symbols),
    )


@pytest.mark.asyncio
async def test_reports_route_and_market_state_per_tracked_symbol() -> None:
    result = await _check(True, FUTURES)

    assert result["providers"] == {
        "binance": {"authenticated": True, "credentialed": False},
        "tradingview": {"authenticated": True, "credentialed": True},
    }
    assert result["symbols"][FUTURES] == {
        "provider": "tradingview",
        "calendar_id": Continuous24x7Calendar().calendar_id,
        "is_market_open": True,
    }
    assert "status" not in result


@pytest.mark.asyncio
async def test_lost_session_on_a_used_provider_is_degraded() -> None:
    result = await _check(False, FUTURES)

    assert result["status"] == "degraded"
    assert result["degraded_providers"] == ["tradingview"]


@pytest.mark.asyncio
async def test_lost_session_on_an_unused_provider_is_not_degraded() -> None:
    result = await _check(False)

    assert result["symbols"] == {}
    assert "status" not in result


@pytest.mark.asyncio
async def test_an_anonymous_session_by_configuration_is_not_degraded() -> None:
    result = await _check(False, FUTURES, credentialed=False)

    assert result["providers"]["tradingview"] == {"authenticated": False, "credentialed": False}
    assert "status" not in result
