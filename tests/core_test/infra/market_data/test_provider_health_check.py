from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.infra.market_data.provider_health_check import check_market_data_providers

CFD = "EURUSD:EXNESS"


def _tracked(*symbols: str) -> MagicMock:
    repo = MagicMock()
    repo.list_all = AsyncMock(return_value=[MagicMock(symbol=s) for s in symbols])
    return repo


def _calendars() -> MagicMock:
    factory = MagicMock()
    factory.for_symbol = AsyncMock(return_value=Continuous24x7Calendar())
    return factory


async def _check(exness_authenticated: bool, *symbols: str, credentialed: bool = True) -> dict:
    return await check_market_data_providers(
        {"binance": lambda: True, "exness": lambda: exness_authenticated},
        {"exness"} if credentialed else set(),
        _calendars(),
        _tracked(*symbols),
    )


@pytest.mark.asyncio
async def test_reports_route_and_market_state_per_tracked_symbol() -> None:
    result = await _check(True, CFD)

    assert result["providers"] == {
        "binance": {"authenticated": True, "credentialed": False},
        "exness": {"authenticated": True, "credentialed": True},
    }
    assert result["symbols"][CFD] == {
        "provider": "exness",
        "calendar_id": Continuous24x7Calendar().calendar_id,
        "is_market_open": True,
    }
    assert "status" not in result


@pytest.mark.asyncio
async def test_lost_session_on_a_used_provider_is_degraded() -> None:
    result = await _check(False, CFD)

    assert result["status"] == "degraded"
    assert result["degraded_providers"] == ["exness"]


@pytest.mark.asyncio
async def test_lost_session_on_an_unused_provider_is_not_degraded() -> None:
    result = await _check(False)

    assert result["symbols"] == {}
    assert "status" not in result


@pytest.mark.asyncio
async def test_an_anonymous_session_by_configuration_is_not_degraded() -> None:
    result = await _check(False, CFD, credentialed=False)

    assert result["providers"]["exness"] == {"authenticated": False, "credentialed": False}
    assert "status" not in result


@pytest.mark.asyncio
async def test_each_symbol_reports_the_provider_its_suffix_names() -> None:
    result = await _check(True, CFD, "BTCUSDT:BINANCE")

    assert result["symbols"][CFD]["provider"] == "exness"
    assert result["symbols"]["BTCUSDT:BINANCE"]["provider"] == "binance"


# One bad tracked symbol must not hide the state of every other one.
@pytest.mark.asyncio
async def test_an_unregistered_suffix_is_reported_on_its_row_not_raised() -> None:
    result = await _check(True, "XAUUSD:MT5", "BTCUSDT:BINANCE")

    assert result["symbols"]["XAUUSD:MT5"]["provider"] is None
    assert "'mt5'" in result["symbols"]["XAUUSD:MT5"]["error"]
    assert result["symbols"]["BTCUSDT:BINANCE"]["provider"] == "binance"
    assert "status" not in result
