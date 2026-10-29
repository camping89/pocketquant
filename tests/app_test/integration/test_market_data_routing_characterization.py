# Describes production as it runs today (every tracked symbol is ...:BINANCE), so these must
# hold however routing picks a provider. The routing adapters are built in one helper each,
# so a construction change touches the helpers, never the assertions.

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from pocketquant.core.config import Settings
from pocketquant.core.domain.bar.entities import SOURCE_REST_SYNC_1M, Bar
from pocketquant.core.domain.shared.enums import AssetClass, Interval
from pocketquant.core.domain.symbol.value_objects import CALENDAR_CRYPTO_24_7
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.market_data.provider_health_check import check_market_data_providers
from pocketquant.core.infra.market_data.routing_data_provider_adapter import (
    RoutingDataProviderAdapter,
)
from pocketquant.core.infra.market_data.routing_realtime_quote_adapter import (
    RoutingRealtimeQuoteAdapter,
)
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.infra.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.core.infra.persistence.symbol_lookup_helper import (
    _CACHE,
    SymbolLookupHelper,
)
from pocketquant.engine.market_data.sync_dtos import SyncSymbolCommand
from pocketquant.engine.market_data.sync_service import SyncService

SYMBOL = "BTCUSDT:BINANCE"
START = datetime(2026, 6, 10, tzinfo=UTC)
COLLECTIONS = ("bars", "symbols", "tracked_symbols", "sync_status")


def _bar(ts: datetime) -> Bar:
    return Bar(
        symbol=SYMBOL,
        interval=Interval.HOUR_1,
        datetime=ts,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=3.0,
        tick_count=0,
    )


def _rest_child(bars: list[Bar] | Exception) -> MagicMock:
    child = MagicMock()
    if isinstance(bars, Exception):
        child.fetch_ohlcv = AsyncMock(side_effect=bars)
    else:
        child.fetch_ohlcv = AsyncMock(return_value=bars)
    child.search_symbols = AsyncMock(return_value=[{"symbol": "BTCUSDT"}])
    child.close = AsyncMock()
    return child


def _realtime_child() -> MagicMock:
    child = MagicMock()
    child.subscribe = AsyncMock(return_value="sub-key")
    child.unsubscribe = AsyncMock()
    return child


def _routing_rest(
    children: dict[str, MagicMock], settings: Settings, lookup: SymbolLookupHelper
) -> RoutingDataProviderAdapter:
    return RoutingDataProviderAdapter(
        providers=children,  # pyright: ignore[reportArgumentType]
    )


def _routing_realtime(
    children: dict[str, MagicMock], settings: Settings, lookup: SymbolLookupHelper
) -> RoutingRealtimeQuoteAdapter:
    return RoutingRealtimeQuoteAdapter(
        providers=children,  # pyright: ignore[reportArgumentType]
    )


async def _health(
    settings: Settings,
    lookup: SymbolLookupHelper,
    calendars: TradingCalendarFactory,
    tracked: TrackedSymbolRepository,
) -> dict:
    return await check_market_data_providers(
        {"binance": lambda: True, "exness": lambda: True},
        set(),
        calendars,
        tracked,
    )


# Nothing is seeded: the symbol arrives unseeded.
@pytest_asyncio.fixture
async def env(settings: Settings):
    database = Database()
    await database.connect(settings)
    cache = Cache()
    await cache.connect(settings)

    repos = {
        "bars": BarRepository(database),
        "symbols": SymbolRepository(database),
        "sync_status": SyncStatusRepository(database),
        "tracked": TrackedSymbolRepository(database),
    }
    await repos["bars"].ensure_indexes()
    await repos["symbols"].ensure_indexes()
    await repos["tracked"].ensure_indexes()
    for name in COLLECTIONS:
        await database.get_collection(name).delete_many({})
    _CACHE.clear()

    lookup = SymbolLookupHelper(repos["symbols"])
    calendars = TradingCalendarFactory(symbol_lookup=lookup)
    try:
        yield database, cache, repos, lookup, calendars
    finally:
        for name in COLLECTIONS:
            await database.get_collection(name).delete_many({})
        _CACHE.clear()
        await cache.disconnect()
        await database.disconnect()


@pytest.mark.asyncio
async def test_an_unseeded_binance_symbol_syncs_through_binance_and_is_stamped_crypto(
    settings: Settings, env
) -> None:
    _, cache, repos, lookup, calendars = env
    bars = [_bar(START + timedelta(hours=i)) for i in range(4)]
    binance, exness = _rest_child(bars), _rest_child([])
    routing = _routing_rest({"binance": binance, "exness": exness}, settings, lookup)

    # Before the first sync the symbol has no document and still reads as 24/7.
    assert (await calendars.for_symbol(SYMBOL)).calendar_id == CALENDAR_CRYPTO_24_7

    result = await SyncService(
        provider=routing,
        cache=cache,
        bar_repository=repos["bars"],
        symbol_repository=repos["symbols"],
        sync_status_repository=repos["sync_status"],
        calendar_factory=calendars,
    ).sync_one(
        SyncSymbolCommand(
            symbol=SYMBOL, interval=Interval.HOUR_1, n_bars=10, source=SOURCE_REST_SYNC_1M
        )
    )

    assert result.bars_synced == 4
    binance.fetch_ohlcv.assert_awaited()
    exness.fetch_ohlcv.assert_not_awaited()

    stored = await repos["bars"].find(SYMBOL, Interval.HOUR_1)
    assert {b.calendar_id for b in stored} == {CALENDAR_CRYPTO_24_7}

    doc = await repos["symbols"].find_by_symbol(SYMBOL)
    assert doc is not None
    assert doc.asset_class is AssetClass.CRYPTO_SPOT
    assert doc.calendar_id == CALENDAR_CRYPTO_24_7


@pytest.mark.asyncio
async def test_a_binance_outage_is_raised_not_reported_as_an_empty_market(
    settings: Settings, env
) -> None:
    _, _, _, lookup, _ = env
    routing = _routing_rest(
        {"binance": _rest_child(RuntimeError("binance down")), "exness": _rest_child([])},
        settings,
        lookup,
    )

    with pytest.raises(RuntimeError, match="binance down"):
        await routing.fetch_ohlcv(SYMBOL, Interval.MINUTE_1, 10)


@pytest.mark.asyncio
async def test_a_quiet_binance_answer_is_an_empty_list(settings: Settings, env) -> None:
    _, _, _, lookup, _ = env
    routing = _routing_rest(
        {"binance": _rest_child([]), "exness": _rest_child([])}, settings, lookup
    )

    assert await routing.fetch_ohlcv(SYMBOL, Interval.MINUTE_1, 10) == []


@pytest.mark.asyncio
async def test_symbol_search_goes_to_binance(settings: Settings, env) -> None:
    _, _, _, lookup, _ = env
    binance, exness = _rest_child([]), _rest_child([])
    routing = _routing_rest({"binance": binance, "exness": exness}, settings, lookup)

    assert await routing.search_symbols("btc") == [{"symbol": "BTCUSDT"}]
    binance.search_symbols.assert_awaited_once_with("btc")
    exness.search_symbols.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_binance_symbol_streams_through_the_binance_child_only(
    settings: Settings, env
) -> None:
    _, _, _, lookup, _ = env
    binance, exness = _realtime_child(), _realtime_child()
    routing = _routing_realtime({"binance": binance, "exness": exness}, settings, lookup)

    assert await routing.subscribe(SYMBOL, lambda _: None) == "sub-key"
    await routing.unsubscribe(SYMBOL)

    binance.subscribe.assert_awaited_once()
    binance.unsubscribe.assert_awaited_once_with(SYMBOL)
    exness.subscribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_health_reports_a_tracked_binance_symbol_on_binance_and_24x7(
    settings: Settings, env
) -> None:
    _, _, repos, lookup, calendars = env
    await repos["tracked"].upsert(TrackedSymbol(symbol=SYMBOL, seeded_from="test"))

    result = await _health(settings, lookup, calendars, repos["tracked"])

    assert result["symbols"][SYMBOL]["provider"] == "binance"
    assert result["symbols"][SYMBOL]["calendar_id"] == CALENDAR_CRYPTO_24_7
    assert result["symbols"][SYMBOL]["is_market_open"] is True
    assert "status" not in result
