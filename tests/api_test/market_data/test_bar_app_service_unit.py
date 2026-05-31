"""Unit tests for BarAppService — throttle, no-Mongo-write, multi-tf state."""

import time
from unittest.mock import AsyncMock

import pytest
from pocketquant.api.market_data.app_services.bar_app_service import (
    BarAppService,
)
from pocketquant.api.market_data.app_services.quote_dto import QuoteTick
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.infrastructure.persistence.redis import Cache
from pocketquant.infrastructure.persistence.repositories.bar_repository import BarRepository


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

    def test_default_intervals_all_6_tfs(self):
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
                timestamp=1000.0,
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
                timestamp=1000.1,  # +100ms
            ),
            symbol_key,
            interval,
        )

        # Cache.set not called again
        assert mock_cache.set.call_count == 1

    @pytest.mark.asyncio
    async def test_force_flush_bypasses_throttle(self, bar_service, mock_cache):
        """force=True bypasses throttle (used on bar roll)."""
        from datetime import UTC, datetime

        from pocketquant.core.domain.bar.services.bar_builder import BarBuilder

        builder = BarBuilder(
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
        from datetime import UTC, datetime

        from pocketquant.core.domain.bar.services.bar_builder import BarBuilder

        bar = BarBuilder(
            symbol="BINANCE:BTC",
            interval=Interval.MINUTE_1,
            bar_start=datetime(2026, 5, 6, 10, 0, tzinfo=UTC),
        )
        bar.add_tick(100.0, 1.0, datetime(2026, 5, 6, 10, 0, 1, tzinfo=UTC))
        bar.add_tick(102.0, 2.0, datetime(2026, 5, 6, 10, 0, 2, tzinfo=UTC))

        await bar_service._save_completed_bar(bar)

        # upsert_bar should NOT be called
        mock_bar_repo.upsert_bar.assert_not_called()

    @pytest.mark.asyncio
    async def test_event_bus_publishes_on_bar_completion(self, bar_service, mock_event_bus):
        """BarCompletedEvent IS published on bar completion."""
        from datetime import UTC, datetime

        from pocketquant.core.domain.bar.services.bar_builder import BarBuilder

        bar = BarBuilder(
            symbol="BINANCE:BTC",
            interval=Interval.MINUTE_5,
            bar_start=datetime(2026, 5, 6, 10, 0, tzinfo=UTC),
        )
        bar.add_tick(100.0, 1.0, datetime(2026, 5, 6, 10, 0, 1, tzinfo=UTC))
        bar.add_tick(102.0, 2.0, datetime(2026, 5, 6, 10, 0, 2, tzinfo=UTC))

        await bar_service._save_completed_bar(bar)

        # Event published
        mock_event_bus.publish.assert_called_once()
        call_args = mock_event_bus.publish.call_args
        event = call_args[0][0]
        assert isinstance(event, BarCompletedEvent)
        assert event.symbol == "BINANCE:BTC"
        assert event.interval == "5m"


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
            timestamp=1000.0,
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
        from datetime import UTC, datetime

        # Tick at 10:00 UTC
        tick1 = QuoteTick(
            symbol="BINANCE:BTC",
            price=100.0,
            volume=1.0,
            timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=UTC).timestamp(),
        )
        await bar_service.add_tick(tick1)

        # Tick at 10:01 UTC (1 min later) — 1m bar rolls, but 5m does not
        tick2 = QuoteTick(
            symbol="BINANCE:BTC",
            price=101.0,
            volume=2.0,
            timestamp=datetime(2026, 5, 6, 10, 1, 0, tzinfo=UTC).timestamp(),
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
            timestamp=1000.0,
        )
        await bar_service.add_tick(tick)

        symbols = bar_service.active_symbols
        assert "BINANCE:BTC" in symbols


class TestCacheKeyInjection:
    """Test that last_update is injected into Redis for staleness calc."""

    @pytest.mark.asyncio
    async def test_cache_includes_last_update(self, bar_service, mock_cache):
        """Redis cache dict includes last_update (Unix seconds)."""
        from datetime import UTC, datetime

        from pocketquant.core.domain.bar.services.bar_builder import BarBuilder

        builder = BarBuilder(
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
        call_kwargs = mock_cache.set.call_args[1]
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
            timestamp=1000.0,
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
