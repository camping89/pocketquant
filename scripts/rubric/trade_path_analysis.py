"""Offline MAE/MFE from the bar path between each trade's entry and exit.

For runs that predate in-engine excursion tracking, this reconstructs how far
each trade ran against (MAE) and in favour of (MFE) the position by scanning bar
high/low inside ``[entry_time, exit_time]``. It is an offline approximation: the
entry bar may contain the fill mid-bar, so extremes can slightly overstate the
true excursion. When the engine writes MAE/MFE natively, read those instead.

Aggregates answer two design questions numerically:
- MFE capture rate — of the favourable move available, how much did the exit
  actually bank (per winning trade).
- MAE-to-stop ratio — how close adverse moves came to the stop distance
  (calibration: <0.5 stop too wide, 0.6-0.85 calibrated, >0.85 too tight).
"""

from __future__ import annotations

import numpy as np

from scripts.rubric.types import TradeRow

# A trade whose bar window covers less than this fraction of its expected 1m
# bars is flagged low_coverage (gaps → understated excursions).
_COVERAGE_FLOOR = 0.5


def _excursion(direction: str, entry: float, hi: float, lo: float) -> tuple[float, float]:
    """(MFE, MAE) for one window. MFE ≥ 0 favourable, MAE ≤ 0 adverse."""
    if direction == "LONG":
        return hi - entry, lo - entry
    # SHORT: favourable = price falls, adverse = price rises.
    return entry - lo, entry - hi


def compute_excursions(
    trades: list[TradeRow], bars: np.ndarray
) -> dict[str, object]:
    """Per-trade MAE/MFE + aggregate diagnostics.

    ``bars`` is the struct array from ``data_access.load_bars`` (datetime as
    float epoch-seconds, sorted). Bars are loaded once per run; each trade slices
    its own window via binary search — no per-trade query.
    """
    if bars.size == 0 or not trades:
        return _empty()

    bar_ts = bars["datetime"]
    mae_list: list[float] = []
    mfe_list: list[float] = []
    mae_r_list: list[float] = []
    mfe_r_list: list[float] = []
    capture_list: list[float] = []
    stop_distances: list[float] = []
    low_coverage = 0

    for t in trades:
        entry_ts = t.entry_time.timestamp()
        exit_ts = t.exit_time.timestamp()
        lo_idx = int(np.searchsorted(bar_ts, entry_ts, side="left"))
        hi_idx = int(np.searchsorted(bar_ts, exit_ts, side="right"))

        # Same-bar or empty slice → fall back to the bar containing entry so the
        # excursion is never a spurious zero.
        if hi_idx <= lo_idx:
            anchor = min(max(lo_idx, 0), bars.size - 1)
            window = bars[anchor : anchor + 1]
        else:
            window = bars[lo_idx:hi_idx]

        if window.size == 0:
            continue

        hi = float(window["high"].max())
        lo = float(window["low"].min())
        mfe, mae = _excursion(t.direction, t.entry_price, hi, lo)
        mfe_list.append(mfe)
        mae_list.append(mae)

        # Coverage: expected one 1m bar per 60s of duration.
        expected = max(t.duration_seconds / 60.0, 1.0)
        if window.size < expected * _COVERAGE_FLOOR:
            low_coverage += 1

        if t.sl_price is not None:
            stop = abs(t.entry_price - t.sl_price)
            if stop > 0:
                stop_distances.append(stop)
                mae_r_list.append(mae / stop)
                mfe_r_list.append(mfe / stop)

        # MFE capture on winners: banked profit / favourable extreme available.
        if t.pnl > 0 and mfe > 0:
            exit_move = (
                t.exit_price - t.entry_price
                if t.direction == "LONG"
                else t.entry_price - t.exit_price
            )
            capture_list.append(exit_move / mfe)

    mae_arr = np.abs(np.asarray(mae_list, dtype=float))
    stop_arr = np.asarray(stop_distances, dtype=float)
    mae_to_stop = (
        float(np.mean(mae_arr) / np.mean(stop_arr))
        if mae_arr.size and stop_arr.size and np.mean(stop_arr) > 0
        else None
    )

    return {
        "mfe_capture_mean": _mean_or_none(capture_list),
        "mae_to_stop_mean": mae_to_stop,
        "mae_r_p50": _pct_or_none(mae_r_list, 50),
        "mae_r_p90": _pct_or_none(mae_r_list, 90),
        "mfe_r_p50": _pct_or_none(mfe_r_list, 50),
        "mfe_r_p90": _pct_or_none(mfe_r_list, 90),
        "low_coverage_trades": low_coverage,
        "total_trades": len(trades),
        "low_coverage": low_coverage > len(trades) * 0.2,
    }


def _empty() -> dict[str, object]:
    return {
        "mfe_capture_mean": None,
        "mae_to_stop_mean": None,
        "mae_r_p50": None,
        "mae_r_p90": None,
        "mfe_r_p50": None,
        "mfe_r_p90": None,
        "low_coverage_trades": 0,
        "total_trades": 0,
        "low_coverage": True,
    }


def _mean_or_none(vals: list[float]) -> float | None:
    return float(np.mean(vals)) if vals else None


def _pct_or_none(vals: list[float], q: int) -> float | None:
    return float(np.percentile(vals, q)) if vals else None
