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


# Shared with the TS chart; a golden fixture locks both runtimes to this definition.
# Consumers threshold rejection_wick_pct themselves.
def detect_engulfing(prev: dict, curr: dict) -> EngulfingResult:
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
