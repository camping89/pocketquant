"""One futures symbol through the real pipeline, against real Mongo and Redis.

Everything Phases 2 and 3 built for session calendars has so far only run on the
24/7 calendar, where most of it is the identity. This drives ``ES1!:CME_MINI``
on the CME calendar through ``SyncService.sync_one``, the integrity scan and the
no-progress anomaly path, with a stub provider in place of TradingView.

The services are constructed directly rather than through ``make_test_app``.
Overriding one DI binding in a built container is not something dishka offers,
and none of these assertions involve HTTP — the same reasoning
``test_sync_backfill_gap_fill.py`` records for skipping the handler graph.

Session 2026-06-10 is the reference throughout. It opens 2026-06-09T22:00Z
(17:00 Chicago, the evening before its own date) and closes 2026-06-10T21:00Z,
which is the property that makes a session calendar different from a 24/7 one.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
import structlog
import structlog.testing

from pocketquant.core.config import Settings
from pocketquant.core.domain.bar.entities import SOURCE_REST_SYNC_1M, Bar
from pocketquant.core.domain.bar.services.bar_builder_domain_service import get_bar_start
from pocketquant.core.domain.shared.enums import AssetClass, Interval
from pocketquant.core.domain.symbol import Symbol
from pocketquant.core.domain.symbol.value_objects import (
    CALENDAR_CME_GLOBEX_EQUITY,
    ContractSpec,
)
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
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
from pocketquant.engine.market_data.app_services.integrity_jobs import check_integrity
from pocketquant.engine.market_data.sync_dtos import SyncSymbolCommand
from pocketquant.engine.market_data.sync_internals import anomaly_log
from pocketquant.engine.market_data.sync_internals.anomaly_log import emit_no_progress
from pocketquant.engine.market_data.sync_service import SyncService

SYMBOL = "ES1!:CME_MINI"
SESSION = date(2026, 6, 10)
SOURCE = SOURCE_REST_SYNC_1M
ES_SPEC = ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0, currency="USD")


class _StubProvider:
    """Returns exactly the bars it was given, ignoring n_bars."""

    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    async def fetch_ohlcv(
        self, symbol: str, interval: Interval, n_bars: int = 1000
    ) -> list[Bar]:
        return [b for b in self._bars if b.interval is interval]

    async def search_symbols(self, query: str) -> list[dict]:
        return []

    async def close(self) -> None:
        return


def _bar(ts: datetime, interval: Interval) -> Bar:
    return Bar(
        symbol=SYMBOL,
        interval=interval,
        datetime=ts,
        open=5800.0,
        high=5810.0,
        low=5795.0,
        close=5805.0,
        volume=1000.0,
        tick_count=0,
    )


@pytest_asyncio.fixture
async def futures_env(settings: Settings):
    """Real Mongo + Redis with ES seeded as an index future on the CME calendar."""
    database = Database()
    await database.connect(settings)
    cache = Cache()
    await cache.connect(settings)

    bar_repo = BarRepository(database)
    symbol_repo = SymbolRepository(database)
    sync_status_repo = SyncStatusRepository(database)
    tracked_repo = TrackedSymbolRepository(database)
    await bar_repo.ensure_indexes()
    await symbol_repo.ensure_indexes()
    await tracked_repo.ensure_indexes()

    for name in ("bars", "symbols", "tracked_symbols", "sync_status"):
        await database.get_collection(name).delete_many({})
    # Module-level TTL cache: a previous test's miss would otherwise mask the seed.
    _CACHE.clear()

    await symbol_repo.upsert(
        Symbol.create(
            symbol=SYMBOL,
            name="E-mini S&P 500 continuous",
            asset_class=AssetClass.INDEX_FUTURE,
            contract_spec=ES_SPEC,
        )
    )
    await tracked_repo.upsert(TrackedSymbol(symbol=SYMBOL, seeded_from="test"))

    calendar_factory = TradingCalendarFactory(symbol_lookup=SymbolLookupHelper(symbol_repo))
    calendar = await calendar_factory.for_symbol(SYMBOL)
    assert calendar.calendar_id == CALENDAR_CME_GLOBEX_EQUITY, "seed must resolve the CME calendar"

    def make_sync(bars: list[Bar]) -> SyncService:
        return SyncService(
            provider=_StubProvider(bars),  # pyright: ignore[reportArgumentType]
            cache=cache,
            bar_repository=bar_repo,
            symbol_repository=symbol_repo,
            sync_status_repository=sync_status_repo,
            calendar_factory=calendar_factory,
        )

    try:
        yield make_sync, bar_repo, calendar
    finally:
        for name in ("bars", "symbols", "tracked_symbols", "sync_status"):
            await database.get_collection(name).delete_many({})
        _CACHE.clear()
        await cache.disconnect()
        await database.disconnect()


@pytest.mark.asyncio
async def test_session_aligned_hourly_bars_all_survive(futures_env) -> None:
    """Bars on the session grid are neither dropped nor stamped as crypto.

    The grid starts at the session open, not at UTC midnight, so a bar at
    22:00Z is aligned here and would be aligned on a 24/7 calendar too — but a
    bar at 22:30Z is aligned on neither, which is what makes the count real.
    """
    make_sync, bar_repo, calendar = futures_env
    open_instant = calendar.session_open(SESSION)
    bars = [_bar(open_instant + timedelta(hours=i), Interval.HOUR_1) for i in range(6)]

    result = await make_sync(bars).sync_one(
        SyncSymbolCommand(symbol=SYMBOL, interval=Interval.HOUR_1, n_bars=10, source=SOURCE)
    )

    assert result.filtered_misaligned == 0
    assert result.bars_synced == 6

    stored = await bar_repo.find(SYMBOL, Interval.HOUR_1)
    assert len(stored) == 6
    assert {b.calendar_id for b in stored} == {CALENDAR_CME_GLOBEX_EQUITY}


@pytest.mark.asyncio
async def test_daily_sync_stamps_the_exchange_session_date(futures_env) -> None:
    """The daily bar's session date is the exchange's day, not the UTC date.

    The bar opens 2026-06-09T22:00Z, so a UTC-date reading would call it the
    9th. The exchange calls it the 10th, and that is what must be stored.
    """
    make_sync, bar_repo, calendar = futures_env
    open_instant = calendar.session_open(SESSION)

    result = await make_sync([_bar(open_instant, Interval.DAY_1)]).sync_one(
        SyncSymbolCommand(symbol=SYMBOL, interval=Interval.DAY_1, n_bars=10, source=SOURCE)
    )

    assert result.bars_synced == 1
    stored = await bar_repo.find(SYMBOL, Interval.DAY_1)
    assert len(stored) == 1
    assert stored[0].session_date == SESSION
    assert stored[0].datetime is not None
    assert stored[0].datetime.astimezone(UTC).day == 9, "the session opens the evening before"


@pytest.mark.asyncio
async def test_integrity_does_not_count_shut_hours_as_missing(futures_env) -> None:
    """Seed exactly the calendar's trading minutes; nothing may be reported missing.

    The window is the scan's own seven days, which always spans a weekend. On a
    24/7 grid the weekend and every overnight break would be expected bars, so
    this is the assertion that proves the grid comes from the calendar.
    """
    _, bar_repo, calendar = futures_env
    # check_integrity reads its own clock, so its window can advance by a minute
    # between here and there. Seed a buffer past both ends: a minute it does not
    # scan costs nothing, while a minute it scans and we skipped is a false gap.
    buffer = timedelta(minutes=5)
    end = get_bar_start(datetime.now(UTC), Interval.MINUTE_1)
    minutes = calendar.trading_minutes(end - timedelta(days=7) - buffer, end + buffer)
    assert minutes, "the reference window must contain trading minutes"

    await bar_repo.insert_many([_bar(m, Interval.MINUTE_1) for m in minutes], source=SOURCE)

    report = await check_integrity(SYMBOL, Interval.MINUTE_1, bar_repo, calendar, days_back=7)

    assert report["missing_count"] == 0
    assert report["misaligned_count"] == 0


@pytest.mark.asyncio
async def test_no_progress_is_silent_while_the_market_is_shut(
    futures_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shut market producing no bars is the schedule working, not an anomaly.

    ``emit_no_progress`` takes no instant — it reads the clock itself — so the
    clock is what the test controls. The real CME calendar still decides whether
    that instant is inside a session; only "now" is faked.
    """
    _, _, calendar = futures_env
    # Saturday 2026-06-13, mid-afternoon UTC: no CME equity session is open.
    shut = datetime(2026, 6, 13, 15, 0, tzinfo=UTC)
    assert not calendar.is_open(shut)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ARG003
            return shut

    monkeypatch.setattr(anomaly_log, "datetime", _FrozenDatetime)
    # A fresh proxy, not the module's own logger. structlog is configured with
    # cache_logger_on_first_use=True, so a module logger used here would stay
    # bound to this config and silently stop being capturable in any later test
    # that reconfigures logging — which is how this test first broke two unit
    # tests in the same run without touching their code.
    monkeypatch.setattr(anomaly_log, "logger", structlog.get_logger("test.anomaly_log"))

    with structlog.testing.capture_logs() as logs:
        emit_no_progress(
            SYMBOL,
            Interval.MINUTE_1,
            bars_fetched=0,
            filtered_misaligned=0,
            filtered_existing=0,
            attempts=3,
            streak=9,
            latest_bar=_bar(shut - timedelta(days=1), Interval.MINUTE_1),
            calendar=calendar,
        )

    assert [e for e in logs if e.get("log_level") in ("warning", "error")] == []
