"""Full-candle engulfing detection shared by the Python strategy and the TS chart.

One definition, two consumers: ``EngulfingStrategyService`` enters only strong patterns;
the chart toggle colors every engulfing strong/weak. Locked across both runtimes
by the golden fixture in ``tests/core_test/.../engulfing_golden_fixture.json``.

Engulfing here means the current bar covers the previous bar on BOTH axes: body
over body (open/close) AND range over range (high/low) — the current wick must
not sit inside the previous wick. Body-only overlap is not enough.

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

    Bullish (→ LONG): prev red, curr green, body engulfs (``open <= prev_close``
    and ``close >= prev_open``) AND range engulfs (``high >= prev_high`` and
    ``low <= prev_low``). Bearish mirrors it.

    ``rejection_wick_pct`` is the wick AGAINST the trade direction over the
    bar range (upper wick for LONG, lower wick for SHORT) — a directional
    close-location quality filter. Consumers threshold it themselves.
    """
    prev_open = float(prev["open"])
    prev_high = float(prev["high"])
    prev_low = float(prev["low"])
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
        and high >= prev_high
        and low <= prev_low
    )
    is_bearish = (
        prev_close > prev_open
        and close < open_
        and open_ >= prev_close
        and close <= prev_open
        and high >= prev_high
        and low <= prev_low
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
