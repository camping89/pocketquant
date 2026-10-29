from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    UnknownDataProviderError,
)
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.market_data.routing_data_provider_adapter import (
    DEFAULT_SEARCH_PROVIDER_ID,
    RoutingDataProviderAdapter,
)


def _bar(symbol: str) -> Bar:
    return Bar(
        symbol=symbol,
        interval=Interval.MINUTE_1,
        datetime=None,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
    )


def _provider(result: list[Bar] | Exception) -> AsyncMock:
    provider = AsyncMock()
    if isinstance(result, Exception):
        provider.fetch_ohlcv = AsyncMock(side_effect=result)
    else:
        provider.fetch_ohlcv = AsyncMock(return_value=result)
    provider.search_symbols = AsyncMock(return_value=[{"symbol": "BTCUSDT"}])
    return provider


def _adapter(providers: dict[str, AsyncMock]) -> RoutingDataProviderAdapter:
    return RoutingDataProviderAdapter(providers=providers)  # pyright: ignore[reportArgumentType]


async def _fetch(adapter: RoutingDataProviderAdapter, symbol: str) -> list[Bar]:
    return await adapter.fetch_ohlcv(symbol=symbol, interval=Interval.MINUTE_1, n_bars=10)


@pytest.mark.asyncio
async def test_a_binance_suffix_is_served_by_binance_only() -> None:
    binance = _provider([_bar("BTCUSDT:BINANCE")])
    exness = _provider([_bar("BTCUSDT:BINANCE"), _bar("BTCUSDT:BINANCE")])

    bars = await _fetch(_adapter({"exness": exness, "binance": binance}), "BTCUSDT:BINANCE")

    assert len(bars) == 1
    binance.fetch_ohlcv.assert_awaited_once_with(
        symbol="BTCUSDT:BINANCE", interval=Interval.MINUTE_1, n_bars=10
    )
    exness.fetch_ohlcv.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_exness_suffix_is_served_by_exness_only() -> None:
    binance = _provider([_bar("XAUUSD:EXNESS")])
    exness = _provider([_bar("XAUUSD:EXNESS")])

    await _fetch(_adapter({"binance": binance, "exness": exness}), "XAUUSD:EXNESS")

    exness.fetch_ohlcv.assert_awaited_once()
    binance.fetch_ohlcv.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_suffix_is_matched_case_insensitively() -> None:
    binance = _provider([_bar("BTCUSDT:BINANCE")])

    assert len(await _fetch(_adapter({"binance": binance}), "btcusdt:binance")) == 1


# Returning nothing would look exactly like a quiet market.
@pytest.mark.asyncio
async def test_an_unknown_suffix_fails_loudly() -> None:
    binance = _provider([_bar("XAUUSD:EXNESS")])

    with pytest.raises(UnknownDataProviderError, match="'exness'"):
        await _fetch(_adapter({"binance": binance}), "XAUUSD:EXNESS")

    binance.fetch_ohlcv.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_symbol_without_a_suffix_fails_loudly() -> None:
    with pytest.raises(UnknownDataProviderError):
        await _fetch(_adapter({"binance": _provider([])}), "BTCUSDT")


@pytest.mark.asyncio
async def test_an_unknown_suffix_is_a_value_error_for_existing_callers() -> None:
    with pytest.raises(ValueError):
        await _fetch(_adapter({"binance": _provider([])}), "XAUUSD:EXNESS")


# A raised provider error makes sync_one log market_data.sync.failed and set the status to
# error. Returning [] would report completed with no progress and leave fetch_with_retry
# retrying the failure as emptiness: three calls at a venue that is rate-limiting us.
@pytest.mark.asyncio
async def test_an_outage_is_raised_rather_than_reported_as_an_empty_market() -> None:
    adapter = _adapter({"exness": _provider(RuntimeError("exness down"))})

    with pytest.raises(RuntimeError, match="exness down"):
        await _fetch(adapter, "XAUUSD:EXNESS")


# Another provider's bars for the same code would be another instrument.
@pytest.mark.asyncio
async def test_a_failing_provider_does_not_fall_back_to_another() -> None:
    binance = _provider([_bar("XAUUSD:EXNESS")])
    adapter = _adapter({"exness": _provider(RuntimeError("down")), "binance": binance})

    with pytest.raises(RuntimeError):
        await _fetch(adapter, "XAUUSD:EXNESS")

    binance.fetch_ohlcv.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_quiet_provider_returns_an_empty_list() -> None:
    assert await _fetch(_adapter({"binance": _provider([])}), "BTCUSDT:BINANCE") == []


@pytest.mark.asyncio
async def test_search_goes_to_the_named_default_provider() -> None:
    assert DEFAULT_SEARCH_PROVIDER_ID == "binance"
    binance, exness = _provider([]), _provider([])

    result = await _adapter({"exness": exness, "binance": binance}).search_symbols("btc")

    assert result == [{"symbol": "BTCUSDT"}]
    binance.search_symbols.assert_awaited_once_with("btc")
    exness.search_symbols.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_without_its_default_provider_registered_returns_nothing() -> None:
    assert await _adapter({"exness": _provider([])}).search_symbols("btc") == []


@pytest.mark.asyncio
async def test_close_reaches_every_child_even_when_one_fails() -> None:
    failing, healthy = _provider([]), _provider([])
    failing.close = AsyncMock(side_effect=RuntimeError("stuck"))

    with pytest.raises(RuntimeError, match="stuck"):
        await _adapter({"exness": failing, "binance": healthy}).close()

    healthy.close.assert_awaited_once()
