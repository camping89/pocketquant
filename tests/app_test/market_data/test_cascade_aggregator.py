"""Unit tests for cascade_aggregator — pure functions, no infra."""

from datetime import UTC, datetime

import pytest
from pocketquant.execution.market_data.app_services.cascade_aggregator import (
    CASCADE_TFS,
    aggregate_ohlcv,
    cascade_for_symbol,
    compute_boundaries,
    tf_seconds,
)
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval


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
        assert result["open"] == 110.0  # first in time
        assert result["close"] == 95.0  # last in time


class TestComputeBoundaries:
    """Test compute_boundaries — overlap semantics (bucket overlaps range)."""

    def test_5m_boundaries(self):
        start = datetime(2026, 5, 6, 10, 2, tzinfo=UTC)
        end = datetime(2026, 5, 6, 10, 13, tzinfo=UTC)
        result = compute_boundaries(Interval.MINUTE_5, start, end)
        # Buckets that overlap [10:02, 10:13): [10:00,10:05), [10:05,10:10), [10:10,10:15)
        assert result == [
            datetime(2026, 5, 6, 10, 0, tzinfo=UTC),
            datetime(2026, 5, 6, 10, 5, tzinfo=UTC),
            datetime(2026, 5, 6, 10, 10, tzinfo=UTC),
        ]

    def test_1h_boundaries(self):
        start = datetime(2026, 5, 6, 10, 30, tzinfo=UTC)
        end = datetime(2026, 5, 6, 13, 15, tzinfo=UTC)
        result = compute_boundaries(Interval.HOUR_1, start, end)
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
        result = compute_boundaries(Interval.DAY_1, start, end)
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
        result = compute_boundaries(Interval.HOUR_1, start, end)
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
        result = compute_boundaries(Interval.HOUR_4, start, end)
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
        result = compute_boundaries(Interval.HOUR_1, start, end)
        assert result == [datetime(2026, 5, 6, 10, 0, tzinfo=UTC)]

    def test_exclusive_end_boundary(self):
        """A bucket starting exactly at range_end is excluded."""
        start = datetime(2026, 5, 6, 10, 0, tzinfo=UTC)
        end = datetime(2026, 5, 6, 10, 5, tzinfo=UTC)
        result = compute_boundaries(Interval.MINUTE_5, start, end)
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
        result = compute_boundaries(Interval.HOUR_4, start, end)
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
        result = compute_boundaries(Interval.DAY_1, start, end)
        assert result == [datetime(2026, 5, 8, 0, 0, tzinfo=UTC)]

    def test_bucket_ending_exactly_at_range_start_excluded(self):
        """If a bucket ends *at* range_start, there is no overlap — exclude it.
        Guards the strict `B + tf_secs > range_start` inequality."""
        # 4h bucket [00:00, 04:00). range starts exactly at 04:00.
        start = datetime(2026, 5, 8, 4, 0, tzinfo=UTC)
        end = datetime(2026, 5, 8, 8, 0, tzinfo=UTC)
        result = compute_boundaries(Interval.HOUR_4, start, end)
        # [00:00, 04:00) ends at 04:00 == range_start → no overlap.
        # [04:00, 08:00) starts at 04:00 < 08:00 → included.
        assert result == [datetime(2026, 5, 8, 4, 0, tzinfo=UTC)]


class TestCascadeForSymbol:
    """Unit tests for cascade_for_symbol — focus on empty repo behavior."""

    @pytest.mark.asyncio
    async def test_cascade_no_1m_bars_returns_zeros(self, mock_bar_repo):
        """Cascade on empty 1m data produces zero counts for all tfs."""
        result = await cascade_for_symbol("BINANCE:BTC", 60, mock_bar_repo)

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
            start_date: datetime = None,
            end_date: datetime = None,
            limit: int = 5000,
        ) -> list[Bar]:
            matching = [b for b in self.bars if b.symbol == symbol and b.interval == interval]
            if start_date and end_date:
                matching = [b for b in matching if start_date <= b.datetime <= end_date]
            # Sort by datetime and return limited results
            return sorted(matching, key=lambda b: b.datetime, reverse=True)[:limit]

        async def get_latest(self, symbol: str, interval: Interval):
            matching = [b for b in self.bars if b.symbol == symbol and b.interval == interval]
            return max(matching, key=lambda b: b.datetime) if matching else None

    return MockBarRepository()
