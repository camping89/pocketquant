"""Pin OhlcvService behavior (ex-GetOHLCVHandler)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.engine.market_data.ohlcv_service import GetOHLCVQuery, OhlcvService


def _bar(dt: datetime) -> MagicMock:
    b = MagicMock()
    b.id = "abc123"
    b.datetime = dt
    b.open = 100.0
    b.high = 105.0
    b.low = 99.0
    b.close = 103.0
    b.volume = 50.0
    return b


@pytest.fixture
def cache() -> AsyncMock:
    c = AsyncMock()
    c.get = AsyncMock(return_value=None)
    c.set = AsyncMock()
    return c


@pytest.fixture
def bar_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def svc(cache, bar_repo) -> OhlcvService:
    return OhlcvService(cache=cache, bar_repository=bar_repo)


@pytest.mark.asyncio
async def test_returns_serialized_bars(svc, cache, bar_repo) -> None:
    dt = datetime(2026, 1, 1, tzinfo=UTC)
    bar_repo.find = AsyncMock(return_value=[_bar(dt)])

    result = await svc.get_ohlcv(GetOHLCVQuery(symbol="BTCUSDT:BINANCE", interval="1d"))

    assert result.symbol == "BTCUSDT:BINANCE"
    assert result.interval == "1d"
    assert result.count == 1
    assert result.data[0]["close"] == 103.0
    assert result.data[0]["datetime"] == dt.isoformat()


@pytest.mark.asyncio
async def test_cache_hit_skips_db(svc, cache, bar_repo) -> None:
    cached_data = [{"id": "x", "close": 50.0}]
    cache.get = AsyncMock(return_value=cached_data)

    result = await svc.get_ohlcv(GetOHLCVQuery(symbol="BTCUSDT:BINANCE", interval="1d"))

    bar_repo.find.assert_not_called()
    assert result.data == cached_data
    assert result.count == 1


@pytest.mark.asyncio
async def test_cache_miss_writes_cache(svc, cache, bar_repo) -> None:
    dt = datetime(2026, 1, 1, tzinfo=UTC)
    bar_repo.find = AsyncMock(return_value=[_bar(dt)])

    await svc.get_ohlcv(GetOHLCVQuery(symbol="BTCUSDT:BINANCE", interval="1d"))

    cache.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_symbol_uppercased(svc, cache, bar_repo) -> None:
    bar_repo.find = AsyncMock(return_value=[])
    result = await svc.get_ohlcv(GetOHLCVQuery(symbol="btcusdt:binance", interval="1d"))
    assert result.symbol == "BTCUSDT:BINANCE"


@pytest.mark.asyncio
async def test_empty_result(svc, cache, bar_repo) -> None:
    bar_repo.find = AsyncMock(return_value=[])
    result = await svc.get_ohlcv(GetOHLCVQuery(symbol="ETHUSDT:BINANCE", interval="1h"))
    assert result.data == []
    assert result.count == 0


@pytest.mark.asyncio
async def test_bar_with_none_datetime_serializes_null(svc, cache, bar_repo) -> None:
    b = _bar(None)  # type: ignore[arg-type]
    b.datetime = None
    bar_repo.find = AsyncMock(return_value=[b])

    result = await svc.get_ohlcv(GetOHLCVQuery(symbol="BTCUSDT:BINANCE", interval="1d"))

    assert result.data[0]["datetime"] is None
