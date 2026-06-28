"""Strict-body engulfing detection shared by the Python strategy and the TS chart.

One definition, two consumers: ``EngulfingStrategy`` enters only strong patterns;
the chart toggle colors every engulfing strong/weak. Locked across both runtimes
by the golden fixture in ``tests/core_test/.../engulfing_golden_fixture.json``.

Pure function, no state, no I/O — stdlib only so the core import contract holds.
"""

from __future__ import annotations

from dataclasses import dataclass

# Sentinel for "no directional rejection signal": a non-engulfing pair or a
# zero-range (doji) bar. Always a float so the fixture compares one numeric path
# in both Python and TS — a JSON null would diverge at exactly these edges.
_NO_SIGNAL_REJECTION = 1.0


@dataclass(frozen=True)
class EngulfingResult:
    is_bullish: bool
    is_bearish: bool
    rejection_wick_pct: float


def detect_engulfing(prev: dict, curr: dict) -> EngulfingResult:
    """Detect strict body engulfing between two consecutive bars.

    Bars are dicts with float ``open/high/low/close``.

    Bullish (→ LONG): prev red, curr green, ``open <= prev_close`` and
    ``close >= prev_open``. Bearish mirrors it.

    ``rejection_wick_pct`` is the wick AGAINST the trade direction over the
    bar range (upper wick for LONG, lower wick for SHORT) — a directional
    close-location quality filter. Consumers threshold it themselves.
    """
    prev_open = float(prev["open"])
    prev_close = float(prev["close"])
    open_ = float(curr["open"])
    high = float(curr["high"])
    low = float(curr["low"])
    close = float(curr["close"])

    is_bullish = (
        prev_close < prev_open
        and close > open_
        and open_ <= prev_close
        and close >= prev_open
    )
    is_bearish = (
        prev_close > prev_open
        and close < open_
        and open_ >= prev_close
        and close <= prev_open
    )

    if not (is_bullish or is_bearish):
        return EngulfingResult(False, False, _NO_SIGNAL_REJECTION)

    range_ = high - low
    if range_ == 0:
        # Zero-range bar fails any quality filter; avoid division by zero.
        rejection_wick_pct = _NO_SIGNAL_REJECTION
    elif is_bullish:
        rejection_wick_pct = (high - close) / range_
    else:
        rejection_wick_pct = (close - low) / range_

    return EngulfingResult(is_bullish, is_bearish, rejection_wick_pct)
