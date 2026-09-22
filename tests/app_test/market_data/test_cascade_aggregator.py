"""Unit tests for cascade_aggregator — pure functions, no infra."""

import threading
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
import structlog

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.calendars.cme_globex_calendar_adapter import CmeGlobexCalendarAdapter
from pocketquant.engine.market_data.app_services.cascade_aggregator import (
    CASCADE_TFS,
    aggregate_ohlcv,
    cascade_for_symbol,
    cascade_tfs,
    compute_boundaries,
    tf_seconds,
)

CALENDAR = Continuous24x7Calendar()
CME = CmeGlobexCalendarAdapter()


class TestTfSeconds:
    """Test tf_seconds converter — pure function."""

    def test_all_supported_intervals(self):
        assert tf_seconds(Interval.MINUTE_1) == 60
        assert tf_seconds(Interval.MINUTE_5) == 300
        assert tf_seconds(Interval.MINUTE_15) == 900
        assert tf_seconds(Interval.HOUR_1) == 3_600
        assert tf_seconds(Interval.HOUR_4) == 14_400
        assert tf_seconds(Interval.DAY_1) == 86_400

    def test_unsupported_interval_raises(self):
        with pytest.raises(ValueError, match="Unsupported cascade interval"):
            tf_seconds(Interval.WEEK_1)


class TestAggregateOhlcv:
    """Test aggregate_ohlcv — pure math, no DB."""

    def test_empty_bars_returns_none(self):
        result = aggregate_ohlcv([])
        assert result is None

    def test_single_bar(self):
        bar = Bar(
            symbol="BINANCE:BTC",
            interval=Interval.MINUTE_1,
            datetime=datetime(2026, 5, 6, 10, 0, tzinfo=UTC),
            open=100.0,
            high=105.0,
            low=95.0,
            close=103.0,
            volume=1000.0,
        )
        result = aggregate_ohlcv([bar])
        assert result == {
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 103.0,
            "volume": 1000.0,
        }

    def test_five_bars_5m_aggregation(self):
        bars = [
            Bar(
                symbol="BINANCE:BTC",
                interval=Interval.MINUTE_1,
                datetime=datetime(2026, 5, 6, 10, i, tzinfo=UTC),
                open=100.0 + i,
                high=105.0 + i,
                low=95.0 + i,
                close=103.0 + i,
                volume=1000.0 * (i + 1),
            )
            for i in range(5)
        ]
        result = aggregate_ohlcv(bars)
        assert result is not None
        assert result["open"] == 100.0  # first
        assert result["close"] == 107.0  # last (103.0 + 4)
        assert result["high"] == 109.0  # max (105.0 + 4)
        assert result["low"] == 95.0  # min
        assert result["volume"] == 15000.0  # sum(1000 * 1 + 1000 * 2 + ... + 1000 * 5)

    def test_partial_aggregate_still_works(self):
        """Partial aggregate (3 of 5 expected) still computes correctly."""
        bars = [
            Bar(
                symbol="BINANCE:BTC",
                interval=Interval.MINUTE_1,
                datetime=datetime(2026, 5, 6, 10, i, tzinfo=UTC),
                open=100.0,
                high=105.0,
                low=95.0,
                close=103.0,
                volume=1000.0,
            )
            for i in range(3)
        ]
        result = aggregate_ohlcv(bars)
        assert result is not None
        assert result["volume"] == 3000.0

    def test_unsorted_bars_ordered_correctly(self):
        """aggregate_ohlcv sorts bars by datetime before extracting first/last."""
        bars = [
            Bar(
                symbol="BINANCE:BTC",
                interval=Interval.MINUTE_1,
                datetime=datetime(2026, 5, 6, 10, 2, tzinfo=UTC),  # out of order
                open=100.0,
                high=105.0,
                low=95.0,
                close=103.0,
                volume=1000.0,
            ),
            Bar(
                symbol="BINANCE:BTC",
                interval=Interval.MINUTE_1,
                datetime=datetime(2026, 5, 6, 10, 0, tzinfo=UTC),
                open=110.0,
                high=115.0,
                low=105.0,
                close=108.0,
                volume=1000.0,
            ),
            Bar(
                symbol="BINANCE:BTC",
                interval=Interval.MINUTE_1,
                datetime=datetime(2026, 5, 6, 10, 4, tzinfo=UTC),
                open=90.0,
                high=100.0,
                low=80.0,
                close=95.0,
                volume=1000.0,
            ),
        ]
        result = aggregate_ohlcv(bars)
        assert result is not None
        assert result["open"] == 110.0  # first in time
        assert result["close"] == 95.0  # last in time


class TestComputeBoundaries:
    """Test compute_boundaries — overlap semantics (bucket overlaps range)."""

    def test_5m_boundaries(self):
        start = datetime(2026, 5, 6, 10, 2, tzinfo=UTC)
        end = datetime(2026, 5, 6, 10, 13, tzinfo=UTC)
        result = compute_boundaries(Interval.MINUTE_5, start, end, CALENDAR)
        # Buckets that overlap [10:02, 10:13): [10:00,10:05), [10:05,10:10), [10:10,10:15)
        assert result == [
            datetime(2026, 5, 6, 10, 0, tzinfo=UTC),
            datetime(2026, 5, 6, 10, 5, tzinfo=UTC),
            datetime(2026, 5, 6, 10, 10, tzinfo=UTC),
        ]

    def test_1h_boundaries(self):
        start = datetime(2026, 5, 6, 10, 30, tzinfo=UTC)
        end = datetime(2026, 5, 6, 13, 15, tzinfo=UTC)
        result = compute_boundaries(Interval.HOUR_1, start, end, CALENDAR)
        # Buckets [10:00,11:00), [11:00,12:00), [12:00,13:00), [13:00,14:00) all overlap.
        assert result == [
            datetime(2026, 5, 6, 10, 0, tzinfo=UTC),
            datetime(2026, 5, 6, 11, 0, tzinfo=UTC),
            datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
            datetime(2026, 5, 6, 13, 0, tzinfo=UTC),
        ]

    def test_1d_boundary_at_midnight(self):
        start = datetime(2026, 5, 6, 15, 0, tzinfo=UTC)
        end = datetime(2026, 5, 8, 10, 0, tzinfo=UTC)
        result = compute_boundaries(Interval.DAY_1, start, end, CALENDAR)
        # Buckets [05-06, 05-07), [05-07, 05-08), [05-08, 05-09) all overlap the range.
        assert result == [
            datetime(2026, 5, 6, 0, 0, tzinfo=UTC),
            datetime(2026, 5, 7, 0, 0, tzinfo=UTC),
            datetime(2026, 5, 8, 0, 0, tzinfo=UTC),
        ]

    def test_hour_boundary_spanning_edge(self):
        """Range spanning hour edge produces correct bucket count."""
        start = datetime(2026, 5, 6, 23, 45, tzinfo=UTC)
        end = datetime(2026, 5, 7, 1, 30, tzinfo=UTC)
        result = compute_boundaries(Interval.HOUR_1, start, end, CALENDAR)
        # Buckets [23:00,00:00), [00:00,01:00), [01:00,02:00) all overlap.
        assert result == [
            datetime(2026, 5, 6, 23, 0, tzinfo=UTC),
            datetime(2026, 5, 7, 0, 0, tzinfo=UTC),
            datetime(2026, 5, 7, 1, 0, tzinfo=UTC),
        ]

    def test_4h_alignment(self):
        """4h boundaries at hour % 4 == 0; bucket containing range_start included."""
        start = datetime(2026, 5, 6, 10, 0, tzinfo=UTC)
        end = datetime(2026, 5, 6, 20, 0, tzinfo=UTC)
        result = compute_boundaries(Interval.HOUR_4, start, end, CALENDAR)
        # Buckets [08:00,12:00), [12:00,16:00), [16:00,20:00) overlap [10:00, 20:00).
        # [20:00, 24:00) starts at range_end → excluded by `B < range_end`.
        assert result == [
            datetime(2026, 5, 6, 8, 0, tzinfo=UTC),
            datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
            datetime(2026, 5, 6, 16, 0, tzinfo=UTC),
        ]

    def test_no_boundaries_when_range_empty(self):
        """1m-wide range still includes the bucket that contains it."""
        start = datetime(2026, 5, 6, 10, 0, tzinfo=UTC)
        end = datetime(2026, 5, 6, 10, 1, tzinfo=UTC)
        result = compute_boundaries(Interval.HOUR_1, start, end, CALENDAR)
        assert result == [datetime(2026, 5, 6, 10, 0, tzinfo=UTC)]

    def test_exclusive_end_boundary(self):
        """A bucket starting exactly at range_end is excluded."""
        start = datetime(2026, 5, 6, 10, 0, tzinfo=UTC)
        end = datetime(2026, 5, 6, 10, 5, tzinfo=UTC)
        result = compute_boundaries(Interval.MINUTE_5, start, end, CALENDAR)
        # [10:00, 10:05) overlaps; [10:05, 10:10) starts at range_end → excluded.
        assert result == [datetime(2026, 5, 6, 10, 0, tzinfo=UTC)]

    # ------- Regression coverage for the cascade-staleness bug -------

    def test_4h_just_closed_bucket_included_for_final_pass(self):
        """4h bucket boundary may be older than range_start, but must still be
        included when its bucket *end* falls inside the range — that's the
        post-close pass that fixes stale 4h aggregates."""
        # Cron at 08:00 UTC, lookback 100m → range_start = 06:20.
        start = datetime(2026, 5, 8, 6, 20, tzinfo=UTC)
        end = datetime(2026, 5, 8, 8, 0, tzinfo=UTC)
        result = compute_boundaries(Interval.HOUR_4, start, end, CALENDAR)
        # Old (boundary-in-range) returned []. New must include 04:00 because
        # [04:00, 08:00) ends exactly at range_end → bucket touched range.
        # However our overlap rule needs B + tf_secs > range_start; 08:00 > 06:20 ✓.
        assert result == [datetime(2026, 5, 8, 4, 0, tzinfo=UTC)]

    def test_1d_today_bucket_kept_alive_through_the_day(self):
        """The current-day 1d bucket must reappear on every cron run, even when
        midnight has slipped outside lookback (otherwise today's daily bar
        freezes ~100m past midnight)."""
        # 14:30 UTC, lookback 100m → range_start = 12:50; midnight is way before.
        start = datetime(2026, 5, 8, 12, 50, tzinfo=UTC)
        end = datetime(2026, 5, 8, 14, 30, tzinfo=UTC)
        result = compute_boundaries(Interval.DAY_1, start, end, CALENDAR)
        assert result == [datetime(2026, 5, 8, 0, 0, tzinfo=UTC)]

    def test_bucket_ending_exactly_at_range_start_excluded(self):
        """If a bucket ends *at* range_start, there is no overlap — exclude it.
        Guards the strict `B + tf_secs > range_start` inequality."""
        # 4h bucket [00:00, 04:00). range starts exactly at 04:00.
        start = datetime(2026, 5, 8, 4, 0, tzinfo=UTC)
        end = datetime(2026, 5, 8, 8, 0, tzinfo=UTC)
        result = compute_boundaries(Interval.HOUR_4, start, end, CALENDAR)
        # [00:00, 04:00) ends at 04:00 == range_start → no overlap.
        # [04:00, 08:00) starts at 04:00 < 08:00 → included.
        assert result == [datetime(2026, 5, 8, 4, 0, tzinfo=UTC)]


class TestCascadeForSymbol:
    """Unit tests for cascade_for_symbol — focus on empty repo behavior."""

    @pytest.mark.asyncio
    async def test_cascade_no_1m_bars_returns_zeros(self, mock_bar_repo):
        """Cascade on empty 1m data produces zero counts for all tfs."""
        result = await cascade_for_symbol("BINANCE:BTC", 60, mock_bar_repo, CALENDAR)

        for tf in CASCADE_TFS:
            assert result[tf] == 0

        # Verify result structure
        assert len(result) == 5  # 5 cascade tfs
        assert Interval.MINUTE_5 in result
        assert Interval.MINUTE_15 in result
        assert Interval.HOUR_1 in result
        assert Interval.HOUR_4 in result
        assert Interval.DAY_1 in result


@pytest.fixture
def mock_bar_repo():
    """Mock BarRepository for cascade tests — in-memory storage."""

    class MockBarRepository:
        def __init__(self):
            self.bars: list[Bar] = []

        async def upsert_bar(self, bar: Bar, *, source: str) -> None:  # noqa: ARG002
            # Remove existing bar with same key
            self.bars = [
                b
                for b in self.bars
                if not (
                    b.symbol == bar.symbol
                    and b.interval == bar.interval
                    and b.datetime == bar.datetime
                )
            ]
            self.bars.append(bar)

        async def find(
            self,
            symbol: str,
            interval: Interval,
            start_date: datetime | None = None,
            end_date: datetime | None = None,
            limit: int = 5000,
        ) -> list[Bar]:
            matching = [
                b
                for b in self.bars
                if b.symbol == symbol and b.interval == interval and b.datetime is not None
            ]
            if start_date and end_date:
                matching = [b for b in matching if start_date <= b.datetime <= end_date]  # type: ignore[operator]
            # Sort by datetime and return limited results
            epoch = datetime.min.replace(tzinfo=UTC)
            return sorted(matching, key=lambda b: b.datetime or epoch, reverse=True)[:limit]

        async def get_latest(self, symbol: str, interval: Interval):
            matching = [b for b in self.bars if b.symbol == symbol and b.interval == interval]
            epoch = datetime.min.replace(tzinfo=UTC)
            return max(matching, key=lambda b: b.datetime or epoch) if matching else None

    return MockBarRepository()


class _FrozenCalendar(ITradingCalendarPort):
    """A calendar that maps every instant onto one bucket.

    No real calendar does this; it exists to drive ``compute_boundaries`` into
    the non-advancing case, which otherwise spins a cron job forever.
    """

    FIXED = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)

    @property
    def calendar_id(self) -> str:
        return "frozen_test"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo("UTC")

    def is_open(self, instant: datetime) -> bool:
        return True

    def session_date(self, instant: datetime) -> date:
        return instant.date()

    def session_open(self, session_date: date) -> datetime:
        return self.FIXED

    def session_close(self, session_date: date) -> datetime:
        return self.FIXED

    def previous_close(self, instant: datetime) -> datetime:
        return instant

    def sessions(self, start: datetime, end: datetime) -> list[date]:
        return [start.date()]

    def trading_minutes(self, start: datetime, end: datetime) -> list[datetime]:
        return []

    def bar_start(self, instant: datetime, interval: Interval) -> datetime:
        return self.FIXED

    def periods_per_year(self, interval: Interval) -> float:
        return 1.0


class TestBoundaryStepFallback:
    """The loop must terminate even when the calendar refuses to advance."""

    def test_non_advancing_calendar_still_terminates_and_says_so(self) -> None:
        start = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 6, 1, 4, 0, tzinfo=UTC)

        # Run on a daemon thread with a deadline: without the fallback this call
        # never returns, and a hung CI job is a far worse signal than a red test.
        # A daemon thread is what lets the rest of the suite finish and the
        # process exit while the runaway loop is still spinning.
        box: list[list[datetime]] = []
        with structlog.testing.capture_logs() as logs:
            worker = threading.Thread(
                target=lambda: box.append(
                    compute_boundaries(Interval.HOUR_1, start, end, _FrozenCalendar())
                ),
                daemon=True,
            )
            worker.start()
            worker.join(timeout=5)

        if worker.is_alive():
            pytest.fail("compute_boundaries did not terminate: the step fallback is gone")

        result = box[0]
        assert len(result) == 4
        fallbacks = [e for e in logs if e.get("event") == "cascade.boundary_step_fallback"]
        assert len(fallbacks) == 4
        assert fallbacks[0]["calendar_id"] == "frozen_test"

    def test_advancing_calendar_logs_no_fallback(self) -> None:
        start = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 6, 1, 4, 0, tzinfo=UTC)

        with structlog.testing.capture_logs() as logs:
            compute_boundaries(Interval.HOUR_1, start, end, CALENDAR)

        assert [e for e in logs if e.get("event") == "cascade.boundary_step_fallback"] == []


class TestExpectedCountComesFromTheCalendar:
    """A bucket's expected bar count is the calendar's, not a constant 60/1440."""

    # 21:00-22:00 UTC is the CME daily maintenance halt: zero trading minutes
    # there, sixty on a market that never closes.
    HALT_START = datetime(2026, 6, 10, 21, 0, tzinfo=UTC)

    async def _cascade_one_bucket(self, calendar, bar_count: int) -> list[dict]:
        bars = [
            Bar(
                symbol="ES1!:CME_MINI",
                interval=Interval.MINUTE_1,
                datetime=self.HALT_START + timedelta(minutes=i),
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1.0,
            )
            for i in range(bar_count)
        ]
        bar_repo = AsyncMock()
        bar_repo.find = AsyncMock(return_value=bars)
        bar_repo.upsert_bar = AsyncMock()

        # Only the hour under test gets a bucket; other timeframes would span
        # the halt differently and their warnings are not what this pins.
        with (
            patch(
                "pocketquant.engine.market_data.app_services.cascade_aggregator.compute_boundaries",
                side_effect=lambda tf, *a: [self.HALT_START] if tf is Interval.HOUR_1 else [],
            ),
            structlog.testing.capture_logs() as logs,
        ):
            await cascade_for_symbol("ES1!:CME_MINI", 60, bar_repo, calendar)
        return [e for e in logs if e.get("event") == "cascade.partial_aggregate"]

    @pytest.mark.asyncio
    async def test_a_halted_hour_expects_nothing_and_reports_no_shortfall(self) -> None:
        partials = await self._cascade_one_bucket(CME, bar_count=3)
        assert partials == []

    @pytest.mark.asyncio
    async def test_the_same_hour_on_a_24x7_calendar_expects_sixty(self) -> None:
        partials = await self._cascade_one_bucket(CALENDAR, bar_count=3)
        hourly = [p for p in partials if p["tf"] == Interval.HOUR_1.value]
        assert hourly and hourly[0]["expected"] == 60
        assert hourly[0]["calendar_id"] == CALENDAR.calendar_id


class TestPartialAggregateLevelTracksWhetherTheBucketClosed:
    """An open bucket is short by arithmetic; a closed one is short by a gap."""

    async def _partials(self, boundary: datetime, bar_count: int) -> list[dict]:
        bars = [
            Bar(
                symbol="BTCUSDT:BINANCE",
                interval=Interval.MINUTE_1,
                datetime=boundary + timedelta(minutes=i),
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1.0,
            )
            for i in range(bar_count)
        ]
        bar_repo = AsyncMock()
        bar_repo.find = AsyncMock(return_value=bars)
        bar_repo.upsert_bar = AsyncMock()

        with (
            patch(
                "pocketquant.engine.market_data.app_services.cascade_aggregator.compute_boundaries",
                side_effect=lambda tf, *a: [boundary] if tf is Interval.HOUR_1 else [],
            ),
            structlog.testing.capture_logs() as logs,
        ):
            await cascade_for_symbol("BTCUSDT:BINANCE", 120, bar_repo, CALENDAR)
        return [e for e in logs if e.get("event") == "cascade.partial_aggregate"]

    @pytest.mark.asyncio
    async def test_the_open_bucket_is_debug(self) -> None:
        """The hour we are inside cannot be complete — that is not news."""
        current_hour = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

        partials = await self._partials(current_hour, bar_count=3)

        assert partials, "expected a shortfall to be reported at some level"
        assert partials[0]["log_level"] == "debug"
        assert partials[0]["in_progress"] is True

    @pytest.mark.asyncio
    async def test_a_closed_bucket_short_of_bars_is_still_a_warning(self) -> None:
        """A finished hour holding 3 of its 60 minutes has really lost bars."""
        past_hour = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)

        partials = await self._partials(past_hour, bar_count=3)

        assert partials, "expected a shortfall to be reported at some level"
        assert partials[0]["log_level"] == "warning"
        assert partials[0]["in_progress"] is False


class TestCascadedBarsCarryTheirCalendar:
    """A cascaded bar records which schedule produced it."""

    async def _upserted(self, calendar, tf: Interval) -> Bar:
        boundary = calendar.bar_start(datetime(2026, 6, 10, 12, 0, tzinfo=UTC), tf)
        bars = [
            Bar(
                symbol="BTCUSDT:BINANCE",
                interval=Interval.MINUTE_1,
                datetime=boundary,
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1.0,
            )
        ]
        bar_repo = AsyncMock()
        bar_repo.find = AsyncMock(return_value=bars)
        bar_repo.upsert_bar = AsyncMock()

        with patch(
            "pocketquant.engine.market_data.app_services.cascade_aggregator.compute_boundaries",
            side_effect=lambda t, *a: [boundary] if t is tf else [],
        ):
            await cascade_for_symbol("BTCUSDT:BINANCE", 60, bar_repo, calendar)

        return bar_repo.upsert_bar.await_args_list[0].args[0]

    @pytest.mark.asyncio
    async def test_daily_bar_carries_calendar_id_and_session_date(self) -> None:
        bar = await self._upserted(CALENDAR, Interval.DAY_1)
        assert bar.calendar_id == CALENDAR.calendar_id
        assert bar.session_date == date(2026, 6, 10)

    @pytest.mark.asyncio
    async def test_intraday_bar_carries_calendar_id_but_no_session_date(self) -> None:
        bar = await self._upserted(CALENDAR, Interval.HOUR_1)
        assert bar.calendar_id == CALENDAR.calendar_id
        assert bar.session_date is None


class TestCascadeTimeframesDependOnTheCalendar:
    """Daily bars are cascaded only where the day begins at UTC midnight."""

    def test_a_continuous_market_cascades_its_daily_bar(self) -> None:
        assert Interval.DAY_1 in cascade_tfs(CALENDAR)
        assert cascade_tfs(CALENDAR) == CASCADE_TFS

    def test_a_session_market_fetches_its_daily_bar_instead(self) -> None:
        tfs = cascade_tfs(CME)
        assert Interval.DAY_1 not in tfs
        # Intraday timeframes are still derived, in the same order.
        assert tfs == [t for t in CASCADE_TFS if t is not Interval.DAY_1]

    @pytest.mark.asyncio
    async def test_a_session_symbol_never_upserts_a_cascaded_daily_bar(self) -> None:
        bar_repo = AsyncMock()
        bar_repo.find = AsyncMock(
            return_value=[
                Bar(
                    symbol="ES1!:CME_MINI",
                    interval=Interval.MINUTE_1,
                    datetime=datetime(2026, 6, 10, 14, 0, tzinfo=UTC),
                    open=1.0,
                    high=1.0,
                    low=1.0,
                    close=1.0,
                    volume=1.0,
                )
            ]
        )
        bar_repo.upsert_bar = AsyncMock()

        await cascade_for_symbol("ES1!:CME_MINI", 60, bar_repo, CME)

        written = [c.args[0].interval for c in bar_repo.upsert_bar.await_args_list]
        assert Interval.DAY_1 not in written
