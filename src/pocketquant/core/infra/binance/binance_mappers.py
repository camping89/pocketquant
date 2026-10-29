from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval

# Domain Interval → (Binance literal, bar duration ms)
INTERVAL_TO_BINANCE: dict[Interval, tuple[str, int]] = {
    Interval.MINUTE_1: ("1m", 60_000),
    Interval.MINUTE_5: ("5m", 5 * 60_000),
    Interval.MINUTE_15: ("15m", 15 * 60_000),
    Interval.HOUR_1: ("1h", 60 * 60_000),
    Interval.HOUR_4: ("4h", 4 * 60 * 60_000),
    Interval.DAY_1: ("1d", 24 * 60 * 60_000),
    Interval.WEEK_1: ("1w", 7 * 24 * 60 * 60_000),
}

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{6,12}$")


def validate_symbol(symbol: str) -> str:
    upper = symbol.strip().upper()
    if not _SYMBOL_RE.match(upper):
        raise ValueError(
            f"Invalid Binance symbol '{symbol}': must be 6-12 uppercase alphanumeric chars"
        )
    return upper


# Binance kline row is positional: [0] open time ms, [1..4] OHLC, [5] base volume,
# [8] trade count.
def kline_to_bar(kline: list[Any], symbol: str, interval: Interval) -> Bar:
    open_time_ms = int(kline[0])
    bar_dt = datetime.fromtimestamp(open_time_ms / 1000, tz=UTC)
    return Bar(
        symbol=symbol.upper(),
        interval=interval,
        datetime=bar_dt,
        open=float(kline[1]),
        high=float(kline[2]),
        low=float(kline[3]),
        close=float(kline[4]),
        volume=float(kline[5]),
        tick_count=int(kline[8]),
    )


# @aggTrade carries no bid/ask or session OHLC; downstream handlers accept None.
def aggtrade_to_quote_dict(event: dict[str, Any], symbol: str) -> dict[str, Any]:
    trade_time_ms = int(event["T"])
    timestamp = datetime.fromtimestamp(trade_time_ms / 1000, tz=UTC)

    return {
        "symbol": symbol.upper(),
        "timestamp": timestamp,
        "last_price": float(event["p"]),
        "volume": float(event["q"]),  # delta — raw per-trade quantity
        "bid": None,
        "ask": None,
        "change": None,
        "change_percent": None,
        "open_price": None,
        "high_price": None,
        "low_price": None,
        "prev_close": None,
    }
