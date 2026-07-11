"""Trade-path MAE/MFE tests — synthetic bars + trades, no DB."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from scripts.rubric.data_access import _BAR_DTYPE
from scripts.rubric.trade_path_analysis import _excursion, compute_excursions
from scripts.rubric.types import TradeRow

_T0 = datetime(2025, 1, 1, 0, 0, 0)


def _bars(highs_lows: list[tuple[float, float]], start: datetime) -> np.ndarray:
    """Build a bar struct array from (high, low) pairs, one bar per minute."""
    arr = np.empty(len(highs_lows), dtype=_BAR_DTYPE)
    for i, (hi, lo) in enumerate(highs_lows):
        ts = (start + timedelta(minutes=i)).timestamp()
        mid = (hi + lo) / 2
        arr[i] = (ts, mid, hi, lo, mid)
    return arr


def _trade(direction, entry, exit_p, sl, pnl, dur_min, offset_min=0) -> TradeRow:
    entry_t = _T0 + timedelta(minutes=offset_min)
    return TradeRow(
        trade_id="t",
        direction=direction,
        entry_price=entry,
        exit_price=exit_p,
        sl_price=sl,
        tp_price=None,
        quantity=1.0,
        pnl=pnl,
        commission=0.0,
        duration_seconds=dur_min * 60.0,
        entry_time=entry_t,
        exit_time=entry_t + timedelta(minutes=dur_min),
    )


def test_excursion_sign_long_and_short():
    # LONG entry 100, high 110, low 95 → MFE +10, MAE -5
    assert _excursion("LONG", 100.0, 110.0, 95.0) == (10.0, -5.0)
    # SHORT mirror → MFE +5 (price fell), MAE -10 (price rose)
    assert _excursion("SHORT", 100.0, 110.0, 95.0) == (5.0, -10.0)


def test_long_excursion_over_window():
    bars = _bars([(101, 99), (105, 98), (103, 100)], _T0)
    t = _trade("LONG", entry=100.0, exit_p=103.0, sl=95.0, pnl=3.0, dur_min=2)
    out = compute_excursions([t], bars)
    # MFE_R over stop distance 5: max high 105 → +5 → +1.0R; MAE min low 98 → -2 → -0.4R
    assert out["mfe_r_p50"] == 1.0
    assert abs(out["mae_r_p50"] - (-0.4)) < 1e-9


def test_same_bar_entry_exit_uses_containing_bar():
    # zero-duration trade: window slice would be empty → falls back to entry bar,
    # not a spurious zero excursion.
    bars = _bars([(110, 90)], _T0)
    t = _trade("LONG", entry=100.0, exit_p=100.0, sl=95.0, pnl=0.0, dur_min=0)
    out = compute_excursions([t], bars)
    assert out["mfe_r_p50"] is not None
    assert out["total_trades"] == 1


def test_empty_inputs():
    out = compute_excursions([], np.empty(0, dtype=_BAR_DTYPE))
    assert out["total_trades"] == 0
    assert out["low_coverage"] is True


def test_mfe_capture_only_on_winners():
    bars = _bars([(106, 99)] * 3, _T0)
    win = _trade("LONG", 100.0, 104.0, 95.0, pnl=4.0, dur_min=2, offset_min=0)
    loss = _trade("LONG", 100.0, 96.0, 95.0, pnl=-4.0, dur_min=2, offset_min=10)
    out = compute_excursions([win, loss], bars)
    # capture computed on the winner only (exit move 4 / MFE 6)
    assert out["mfe_capture_mean"] is not None
    assert 0 < out["mfe_capture_mean"] <= 1.5
