"""Unit tests for BarBuilder — delta-semantics volume aggregation.

All tests exercise BarBuilder.add_tick() with per-tick DELTA volume
as per the documented contract. No I/O, no clock dependency.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pocketquant.core.domain.bar.services.bar_builder import BarBuilder
from pocketquant.core.domain.shared.enums import Interval

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BAR_START = datetime(2026, 5, 8, 10, 0, 0, tzinfo=UTC)
BAR_END = BAR_START + timedelta(seconds=60)  # 1m bar


@pytest.fixture
def builder() -> BarBuilder:
    """Fresh 1-minute BarBuilder aligned to BAR_START."""
    return BarBuilder(
        symbol="BTC",
        exchange="BINANCE",
        interval=Interval.MINUTE_1,
        bar_start=BAR_START,
    )


def _tick_ts(offset_s: int = 1) -> datetime:
    """Return a timestamp inside the bar window."""
    return BAR_START + timedelta(seconds=offset_s)


# ---------------------------------------------------------------------------
# Delta semantics
# ---------------------------------------------------------------------------


class TestDeltaSemantics:
    """BarBuilder.add_tick sums per-tick delta volumes correctly."""

    def test_single_delta_tick(self, builder: BarBuilder) -> None:
        """Single tick with delta=0.5 → bar.volume == 0.5."""
        result = builder.add_tick(100.0, 0.5, _tick_ts(1))

        assert result is True
        assert builder.volume == pytest.approx(0.5)

    def test_sum_of_deltas(self, builder: BarBuilder) -> None:
        """Three delta ticks 0.5 + 0.3 + 0.2 → bar.volume == 1.0."""
        builder.add_tick(100.0, 0.5, _tick_ts(1))
        builder.add_tick(101.0, 0.3, _tick_ts(2))
        builder.add_tick(102.0, 0.2, _tick_ts(3))

        assert builder.volume == pytest.approx(1.0)

    def test_zero_delta_tick_updates_ohlc(self, builder: BarBuilder) -> None:
        """Zero-volume tick is accepted; OHLC updates, volume stays 0.0."""
        result = builder.add_tick(100.0, 0.0, _tick_ts(1))

        assert result is True
        assert builder.volume == pytest.approx(0.0)
        # OHLC must still update
        assert builder.open == 100.0
        assert builder.high == 100.0
        assert builder.low == 100.0
        assert builder.close == 100.0
        assert builder.tick_count == 1

    def test_none_volume_does_not_accumulate(self, builder: BarBuilder) -> None:
        """Two None-volume ticks → volume stays 0.0, OHLC still updates."""
        builder.add_tick(100.0, None, _tick_ts(1))
        builder.add_tick(101.0, None, _tick_ts(2))

        assert builder.volume == pytest.approx(0.0)
        assert builder.open == 100.0
        assert builder.close == 101.0
        assert builder.tick_count == 2

    def test_mix_none_then_delta(self, builder: BarBuilder) -> None:
        """None tick followed by delta tick → volume == delta only."""
        builder.add_tick(100.0, None, _tick_ts(1))
        builder.add_tick(101.0, 0.5, _tick_ts(2))

        assert builder.volume == pytest.approx(0.5)

    def test_out_of_bar_tick_rejected(self, builder: BarBuilder) -> None:
        """Tick timestamped after bar_end is rejected; state unchanged."""
        # Record state before
        before_volume = builder.volume
        before_open = builder.open
        before_tick_count = builder.tick_count

        ts_after_end = BAR_END + timedelta(seconds=1)
        result = builder.add_tick(200.0, 0.5, ts_after_end)

        assert result is False
        assert builder.volume == before_volume
        assert builder.open == before_open
        assert builder.tick_count == before_tick_count
