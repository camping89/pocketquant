"""Trade stats calculator — parity with the former FE stats-utils semantics."""

from __future__ import annotations

from datetime import datetime, timedelta

from pocketquant.backtest.domain.services.trade_stats_calculator import (
    drawdown_periods,
    histogram,
    profit_factor_by_direction,
    win_loss_streaks,
)
from pocketquant.core.domain.backtest.value_objects import EquityPoint

T0 = datetime(2026, 1, 1, 0, 0, 0)


def _eq(offset_hours: int, equity: float, drawdown: float) -> EquityPoint:
    return EquityPoint(
        timestamp=T0 + timedelta(hours=offset_hours), equity=equity, drawdown=drawdown
    )


class TestHistogram:
    def test_empty_input_returns_empty(self) -> None:
        assert histogram([]) == []

    def test_equal_values_collapse_to_single_bin(self) -> None:
        bins = histogram([5.0, 5.0, 5.0])
        assert len(bins) == 1
        assert bins[0].count == 3

    def test_max_clamped_into_last_bin(self) -> None:
        # Values spanning [0, 10] with 20 bins: the max must not fall off the
        # half-open top edge.
        bins = histogram([0.0, 10.0], bin_count=20)
        assert sum(b.count for b in bins) == 2

    def test_bin_count_and_span(self) -> None:
        bins = histogram([0.0, 1.0, 2.0, 3.0, 4.0], bin_count=4)
        assert len(bins) == 4
        assert bins[0].lo == 0.0
        assert bins[-1].hi == 4.0
        assert sum(b.count for b in bins) == 5


class TestWinLossStreaks:
    def test_breakeven_resets_streak(self) -> None:
        s = win_loss_streaks([1.0, 1.0, 0.0, 1.0])
        assert s.max_win_streak == 2
        assert s.max_loss_streak == 0

    def test_tracks_both_directions(self) -> None:
        s = win_loss_streaks([1.0, 1.0, 1.0, -1.0, -1.0, 1.0])
        assert s.max_win_streak == 3
        assert s.max_loss_streak == 2

    def test_empty(self) -> None:
        s = win_loss_streaks([])
        assert s.max_win_streak == 0
        assert s.max_loss_streak == 0


class TestProfitFactorByDirection:
    def test_none_when_no_loss(self) -> None:
        pf = profit_factor_by_direction([("LONG", 5.0), ("LONG", 3.0)])
        assert pf.long is None
        assert pf.short is None

    def test_ratio_per_side(self) -> None:
        pf = profit_factor_by_direction(
            [("LONG", 10.0), ("LONG", -5.0), ("SHORT", 4.0), ("SHORT", -8.0)]
        )
        assert pf.long == 2.0
        assert pf.short == 0.5


class TestDrawdownPeriods:
    def test_recovered_period(self) -> None:
        curve = [_eq(0, 100, 0.0), _eq(1, 90, -0.1), _eq(2, 80, -0.2), _eq(3, 100, 0.0)]
        periods = drawdown_periods(curve)
        assert len(periods) == 1
        assert periods[0].depth == -0.2
        assert periods[0].recovery_time is not None

    def test_unrecovered_tail_has_no_recovery(self) -> None:
        curve = [_eq(0, 100, 0.0), _eq(1, 90, -0.1), _eq(2, 85, -0.15)]
        periods = drawdown_periods(curve)
        assert len(periods) == 1
        assert periods[0].recovery_time is None
        assert periods[0].depth == -0.15

    def test_sorted_deepest_first_and_top_n(self) -> None:
        curve = [
            _eq(0, 100, 0.0),
            _eq(1, 95, -0.05),
            _eq(2, 100, 0.0),
            _eq(3, 70, -0.3),
            _eq(4, 100, 0.0),
            _eq(5, 90, -0.1),
            _eq(6, 100, 0.0),
        ]
        periods = drawdown_periods(curve, top_n=2)
        assert len(periods) == 2
        assert periods[0].depth == -0.3
        assert periods[1].depth == -0.1

    def test_no_drawdown(self) -> None:
        curve = [_eq(0, 100, 0.0), _eq(1, 110, 0.0)]
        assert drawdown_periods(curve) == []
