"""Unit tests for BarAppService — throttle, no-Mongo-write, multi-tf state."""

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.calendars.exness_session_calendar_adapter import EXNESS_CALENDARS
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.market_data.app_services.bar_app_service import (
    BarAppService,
)
from pocketquant.engine.market_data.app_services.quote_dto import QuoteTick


@pytest.fixture
def mock_cache():
    """Mock Redis Cache."""
    cache = AsyncMock(spec=Cache)
    cache.set = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.delete_pattern = AsyncMock()
    return cache


@pytest.fixture
def mock_bar_repo():
    """Mock BarRepository."""
    repo = AsyncMock(spec=BarRepository)
    repo.upsert_bar = AsyncMock()
    return repo


@pytest.fixture
def mock_event_bus():
    """Mock EventBus."""
    bus = AsyncMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def bar_service(mock_cache, mock_bar_repo, mock_event_bus):
    """BarAppService with mocked dependencies."""
    return BarAppService(
        cache=mock_cache,
        bar_repository=mock_bar_repo,
        event_bus=mock_event_bus,
        intervals=[Interval.MINUTE_1, Interval.MINUTE_5],
    )


class TestBarAppServiceDefaults:
    """Test BarAppService initialization with defaults."""

    def test_default_intervals_all_canonical_tfs(self):
        cache = AsyncMock(spec=Cache)
        bar_repo = AsyncMock(spec=BarRepository)
        event_bus = AsyncMock(spec=EventBus)

        service = BarAppService(
            cache=cache,
            bar_repository=bar_repo,
            event_bus=event_bus,
        )

        assert service.intervals == [
            Interval.MINUTE_1,
            Interval.MINUTE_5,
            Interval.MINUTE_15,
            Interval.HOUR_1,
            Interval.HOUR_4,
            Interval.DAY_1,
            Interval.WEEK_1,
        ]

    def test_custom_intervals_override_default(self):
        cache = AsyncMock(spec=Cache)
        bar_repo = AsyncMock(spec=BarRepository)
        event_bus = AsyncMock(spec=EventBus)

        service = BarAppService(
            cache=cache,
            bar_repository=bar_repo,
            event_bus=event_bus,
            intervals=[Interval.MINUTE_1, Interval.MINUTE_5],
        )

        assert service.intervals == [Interval.MINUTE_1, Interval.MINUTE_5]


class TestThrottle:
    """Test 200ms throttle on Redis cache writes."""

    @pytest.mark.asyncio
    async def test_throttle_skips_rapid_writes(self, bar_service, mock_cache):
        """Ticks within 200ms → skip Redis write."""
        symbol_key = "BINANCE:BTC"
        interval = Interval.MINUTE_1

        # First tick → write
        await bar_service._process_tick_for_interval(
            QuoteTick(
                symbol="BINANCE:BTC",
                price=100.0,
                volume=1.0,
                timestamp=datetime.fromtimestamp(1000.0, tz=UTC),
            ),
            symbol_key,
            interval,
        )

        assert mock_cache.set.call_count == 1

        # Second tick 100ms later → throttled, no write
        await bar_service._process_tick_for_interval(
            QuoteTick(
                symbol="BINANCE:BTC",
                price=101.0,
                volume=2.0,
                timestamp=datetime.fromtimestamp(1000.1, tz=UTC),  # +100ms
            ),
            symbol_key,
            interval,
        )

        # Cache.set not called again
        assert mock_cache.set.call_count == 1

    @pytest.mark.asyncio
    async def test_force_flush_bypasses_throttle(self, bar_service, mock_cache):
        """force=True bypasses throttle (used on bar roll)."""
        from pocketquant.core.domain.bar.services.bar_builder_domain_service import (
            BarBuilderDomainService,
        )

        builder = BarBuilderDomainService(
            symbol="BINANCE:BTC",
            interval=Interval.MINUTE_1,
            bar_start=datetime(2026, 5, 6, 10, 0, tzinfo=UTC),
        )
        builder.add_tick(100.0, 1.0, datetime(2026, 5, 6, 10, 0, 1, tzinfo=UTC))

        # Even if throttle would normally block, force=True writes
        await bar_service._cache_current_bar("BINANCE:BTC", Interval.MINUTE_1, builder, force=True)

        assert mock_cache.set.called


class TestNoMongoWrite:
    """Test that BarAppService does NOT call bar_repo.upsert_bar."""

    @pytest.mark.asyncio
    async def test_bar_completion_no_mongo_write(self, bar_service, mock_bar_repo):
        """On bar completion, upsert_bar is NOT called."""
        from pocketquant.core.domain.bar.services.bar_builder_domain_service import (
            BarBuilderDomainService,
        )

        bar = BarBuilderDomainService(
            symbol="BINANCE:BTC",
            interval=Interval.MINUTE_1,
            bar_start=datetime(2026, 5, 6, 10, 0, tzinfo=UTC),
        )
        bar.add_tick(100.0, 1.0, datetime(2026, 5, 6, 10, 0, 1, tzinfo=UTC))
        bar.add_tick(102.0, 2.0, datetime(2026, 5, 6, 10, 0, 2, tzinfo=UTC))

        await bar_service._complete_bar(
            bar, Continuous24x7Calendar(), closed_by="tick", closing_tick_at=None
        )

        # upsert_bar should NOT be called
        mock_bar_repo.upsert_bar.assert_not_called()

    @pytest.mark.asyncio
    async def test_event_bus_publishes_on_bar_completion(self, bar_service, mock_event_bus):
        """BarCompletedEvent IS published on bar completion."""
        for ts in (
            datetime(2026, 5, 6, 12, 0, 1, tzinfo=UTC),
            datetime(2026, 5, 6, 12, 5, 1, tzinfo=UTC),
        ):
            tick = QuoteTick(symbol="BINANCE:BTC", price=100.0, volume=1.0, timestamp=ts)
            await bar_service.add_tick(tick)

        # The second tick closes the 12:00 bar of both intervals.
        events = [c[0][0] for c in mock_event_bus.publish.call_args_list]
        assert all(isinstance(e, BarCompletedEvent) for e in events)
        assert [(e.symbol, e.interval) for e in events] == [
            ("BINANCE:BTC", "1m"),
            ("BINANCE:BTC", "5m"),
        ]


class TestMultiTfState:
    """Test multi-timeframe independent state management."""

    @pytest.mark.asyncio
    async def test_multiple_tfs_independent_bars(self, bar_service):
        """Each tf maintains independent in-progress bar state."""
        # Add tick for 1m and 5m simultaneously
        tick = QuoteTick(
            symbol="BINANCE:BTC",
            price=100.0,
            volume=1.0,
            timestamp=datetime.fromtimestamp(1000.0, tz=UTC),
        )

        await bar_service.add_tick(tick)

        # Both tfs should have a bar builder in state
        symbol_key = "BINANCE:BTC"
        assert Interval.MINUTE_1 in bar_service._bars[symbol_key]
        assert Interval.MINUTE_5 in bar_service._bars[symbol_key]

        # Bars are independent
        bar_1m = bar_service._bars[symbol_key][Interval.MINUTE_1]
        bar_5m = bar_service._bars[symbol_key][Interval.MINUTE_5]
        assert bar_1m.close == 100.0
        assert bar_5m.close == 100.0

    @pytest.mark.asyncio
    async def test_5m_bar_rolls_only_on_5min_boundary(self, bar_service):
        """5m bar only completes at 5-minute boundaries, not at every 1m roll."""
        # Tick at 10:00 UTC
        tick1 = QuoteTick(
            symbol="BINANCE:BTC",
            price=100.0,
            volume=1.0,
            timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=UTC),
        )
        await bar_service.add_tick(tick1)

        # Tick at 10:01 UTC (1 min later) — 1m bar rolls, but 5m does not
        tick2 = QuoteTick(
            symbol="BINANCE:BTC",
            price=101.0,
            volume=2.0,
            timestamp=datetime(2026, 5, 6, 10, 1, 0, tzinfo=UTC),
        )
        await bar_service.add_tick(tick2)

        symbol_key = "BINANCE:BTC"
        bar_1m = bar_service._bars[symbol_key][Interval.MINUTE_1]
        bar_5m = bar_service._bars[symbol_key][Interval.MINUTE_5]

        # 1m bar rolled to 10:01
        assert bar_1m.bar_start.hour == 10
        assert bar_1m.bar_start.minute == 1
        # 5m bar still at 10:00 (hasn't rolled yet)
        assert bar_5m.bar_start.hour == 10
        assert bar_5m.bar_start.minute == 0

    @pytest.mark.asyncio
    async def test_active_symbols_tracks_all_tfs(self, bar_service):
        """active_symbols lists all symbols with any in-progress bar."""
        tick = QuoteTick(
            symbol="BINANCE:BTC",
            price=100.0,
            volume=1.0,
            timestamp=datetime.fromtimestamp(1000.0, tz=UTC),
        )
        await bar_service.add_tick(tick)

        symbols = bar_service.active_symbols
        assert "BINANCE:BTC" in symbols


class TestCacheKeyInjection:
    """Test that last_update is injected into Redis for staleness calc."""

    @pytest.mark.asyncio
    async def test_cache_includes_last_update(self, bar_service, mock_cache):
        """Redis cache dict includes last_update (Unix seconds)."""
        from pocketquant.core.domain.bar.services.bar_builder_domain_service import (
            BarBuilderDomainService,
        )

        builder = BarBuilderDomainService(
            symbol="BINANCE:BTC",
            interval=Interval.MINUTE_1,
            bar_start=datetime(2026, 5, 6, 10, 0, tzinfo=UTC),
        )
        builder.add_tick(100.0, 1.0, datetime(2026, 5, 6, 10, 0, 1, tzinfo=UTC))

        before = time.time()
        await bar_service._cache_current_bar("BINANCE:BTC", Interval.MINUTE_1, builder, force=True)
        after = time.time()

        # Verify cache.set was called with last_update in the dict
        assert mock_cache.set.called
        bar_dict = mock_cache.set.call_args[0][1]
        assert "last_update" in bar_dict
        assert before <= bar_dict["last_update"] <= after


class TestFlushAllBars:
    """Test flush_all_bars cleanup on shutdown."""

    @pytest.mark.asyncio
    async def test_flush_clears_state(self, bar_service, mock_event_bus):
        """flush_all_bars clears in-memory state."""
        tick = QuoteTick(
            symbol="BINANCE:BTC",
            price=100.0,
            volume=1.0,
            timestamp=datetime.fromtimestamp(1000.0, tz=UTC),
        )
        await bar_service.add_tick(tick)

        # Verify state exists
        assert len(bar_service._bars) > 0
        assert len(bar_service._last_flush_ts) > 0

        # Flush
        count = await bar_service.flush_all_bars()

        # State cleared
        assert len(bar_service._bars) == 0
        assert len(bar_service._last_flush_ts) == 0
        # Events published for any non-empty bars
        assert count > 0


class _OneCalendar:
    """Stands in for TradingCalendarFactory: every symbol is on ``calendar``."""

    def __init__(self, calendar: ITradingCalendarPort) -> None:
        self._calendar = calendar

    async def for_symbol(self, composite: str) -> ITradingCalendarPort:
        return self._calendar


class _ShortWeekCalendar(Continuous24x7Calendar):
    """Two weeks whose boundary comes an hour early, as a session week's does
    when US clocks spring forward: the second week opens 6 days 23 hours after
    the first. Every other interval keeps the 24/7 grid."""

    FIRST_WEEK = datetime(2027, 3, 7, 23, 0, tzinfo=UTC)
    SECOND_WEEK = datetime(2027, 3, 14, 22, 0, tzinfo=UTC)

    def bar_start(self, instant: datetime, interval: Interval) -> datetime:
        if interval != Interval.WEEK_1:
            return super().bar_start(instant, interval)
        return self.SECOND_WEEK if instant >= self.SECOND_WEEK else self.FIRST_WEEK


class TestSessionCalendarBuckets:
    """Realtime bars open on the symbol's calendar grid, not on the 24/7 one."""

    @pytest.mark.asyncio
    async def test_exness_weekly_bar_opens_on_sunday_and_holds_the_sunday_session(
        self, mock_cache, mock_bar_repo, mock_event_bus
    ):
        service = BarAppService(
            cache=mock_cache,
            bar_repository=mock_bar_repo,
            event_bus=mock_event_bus,
            intervals=[Interval.HOUR_4, Interval.DAY_1, Interval.WEEK_1],
            calendar_factory=_OneCalendar(EXNESS_CALENDARS[0]),  # type: ignore[arg-type]
        )
        symbol = "EURUSD:EXNESS"
        # EURUSD opens Sunday 2026-10-11 at 21:05 UTC. On the 24/7 grid that
        # evening belongs to the week of Monday 10-05, and Monday's tick would
        # close it; on Exness both ticks are in the week of Sunday 10-11.
        for ts, price in (
            (datetime(2026, 10, 11, 21, 30, tzinfo=UTC), 1.1600),
            (datetime(2026, 10, 12, 2, 30, tzinfo=UTC), 1.1601),
        ):
            await service.add_tick(QuoteTick(symbol=symbol, timestamp=ts, price=price, volume=1.0))

        week_open = datetime(2026, 10, 11, 0, 0, tzinfo=UTC)
        monday = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
        assert service._bars[symbol][Interval.WEEK_1].bar_start == week_open
        assert service._bars[symbol][Interval.DAY_1].bar_start == monday
        assert service._bars[symbol][Interval.HOUR_4].bar_start == monday
        completed = [c.args[0] for c in mock_event_bus.publish.await_args_list]
        assert [(e.interval, e.bar_start) for e in completed] == [
            (Interval.HOUR_4.value, datetime(2026, 10, 11, 20, 0, tzinfo=UTC)),
            (Interval.DAY_1.value, week_open),
        ]

    @pytest.mark.asyncio
    async def test_a_bucket_shorter_than_its_interval_still_closes_on_time(
        self, mock_cache, mock_bar_repo, mock_event_bus
    ):
        # The new week opens an hour short of seven days after the old one, so
        # its first tick comes before old open + 7 days. It must still close it.
        service = BarAppService(
            cache=mock_cache,
            bar_repository=mock_bar_repo,
            event_bus=mock_event_bus,
            intervals=[Interval.WEEK_1],
            calendar_factory=_OneCalendar(_ShortWeekCalendar()),  # type: ignore[arg-type]
        )
        symbol = "X:Y"
        for ts, price in (
            (datetime(2027, 3, 8, 15, 0, tzinfo=UTC), 6600.0),
            (datetime(2027, 3, 14, 22, 30, tzinfo=UTC), 6610.0),
        ):
            await service.add_tick(QuoteTick(symbol=symbol, timestamp=ts, price=price, volume=1.0))

        new_week = service._bars[symbol][Interval.WEEK_1]
        assert new_week.bar_start == datetime(2027, 3, 14, 22, 0, tzinfo=UTC)
        assert new_week.close == 6610.0
        completed = [c.args[0] for c in mock_event_bus.publish.await_args_list]
        assert [e.bar_start for e in completed] == [datetime(2027, 3, 7, 23, 0, tzinfo=UTC)]
