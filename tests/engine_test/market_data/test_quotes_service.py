"""Pin QuoteQueryService behavior (ex-GetLatestQuoteHandler)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pocketquant.engine.market_data.quotes_service import (
    GetLatestQuoteQuery,
    QuoteQueryService,
    QuoteResponse,
)


def _cache_dict(symbol: str = "BTCUSDT:BINANCE") -> dict:
    return {
        "symbol": symbol,
        "timestamp": datetime(2026, 1, 1, 12, 0, tzinfo=UTC).isoformat(),
        "last_price": 50000.0,
        "bid": 49990.0,
        "ask": 50010.0,
        "volume": 1234.5,
        "change": 500.0,
        "change_percent": 1.01,
        "open_price": 49500.0,
        "high_price": 51000.0,
        "low_price": 49000.0,
    }


@pytest.mark.asyncio
async def test_returns_quote_response_when_cache_hit() -> None:
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=_cache_dict())
    svc = QuoteQueryService(cache=cache)

    result = await svc.get_latest(GetLatestQuoteQuery(symbol="BTCUSDT:BINANCE"))

    assert isinstance(result, QuoteResponse)
    assert result.symbol == "BTCUSDT:BINANCE"
    assert result.last_price == 50000.0


@pytest.mark.asyncio
async def test_returns_none_when_cache_miss() -> None:
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    svc = QuoteQueryService(cache=cache)

    result = await svc.get_latest(GetLatestQuoteQuery(symbol="BTCUSDT:BINANCE"))

    assert result is None


@pytest.mark.asyncio
async def test_symbol_uppercased_for_cache_key() -> None:
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    svc = QuoteQueryService(cache=cache)

    await svc.get_latest(GetLatestQuoteQuery(symbol="btcusdt:binance"))

    # Cache key must use upper-cased symbol.
    called_key = cache.get.call_args[0][0]
    assert "BTCUSDT:BINANCE" in called_key


@pytest.mark.asyncio
async def test_all_fields_propagated() -> None:
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=_cache_dict())
    svc = QuoteQueryService(cache=cache)

    result = await svc.get_latest(GetLatestQuoteQuery(symbol="BTCUSDT:BINANCE"))

    assert result is not None
    assert result.bid == 49990.0
    assert result.ask == 50010.0
    assert result.volume == 1234.5
    assert result.open_price == 49500.0
    assert result.high_price == 51000.0
    assert result.low_price == 49000.0
