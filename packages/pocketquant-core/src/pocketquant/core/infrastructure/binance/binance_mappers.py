"""Binance data mappers — interval mapping, kline → Bar, aggTrade → quote dict.

Centralises all Binance-specific field translations so client modules stay thin.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval

# ---------------------------------------------------------------------------
# Interval map: Domain Interval → (Binance literal, bar duration ms)
# ---------------------------------------------------------------------------

INTERVAL_TO_BINANCE: dict[Interval, tuple[str, int]] = {
    Interval.MINUTE_1: ("1m", 60_000),
    Interval.MINUTE_3: ("3m", 3 * 60_000),
    Interval.MINUTE_5: ("5m", 5 * 60_000),
    Interval.MINUTE_15: ("15m", 15 * 60_000),
    Interval.MINUTE_30: ("30m", 30 * 60_000),
    Interval.HOUR_1: ("1h", 60 * 60_000),
    Interval.HOUR_2: ("2h", 2 * 60 * 60_000),
    Interval.HOUR_4: ("4h", 4 * 60 * 60_000),
    Interval.DAY_1: ("1d", 24 * 60 * 60_000),
    Interval.WEEK_1: ("1w", 7 * 24 * 60 * 60_000),
    Interval.MONTH_1: ("1M", 30 * 24 * 60 * 60_000),  # approximate; Binance defines calendar month
    # NOTE: HOUR_6, HOUR_8, HOUR_12, DAY_3 omitted — not in current Interval enum.
    # Add when enum is extended (Phase 02 or later).
}

# ---------------------------------------------------------------------------
# Symbol validation
# ---------------------------------------------------------------------------

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{6,12}$")


def validate_symbol(symbol: str) -> str:
    """Return uppercase symbol after validating format (A-Z0-9, length 6-12).

    Raises ValueError on invalid input to prevent URL injection.
    """
    upper = symbol.strip().upper()
    if not _SYMBOL_RE.match(upper):
        raise ValueError(
            f"Invalid Binance symbol '{symbol}': must be 6-12 uppercase alphanumeric chars"
        )
    return upper


# ---------------------------------------------------------------------------
# Kline → Bar
# ---------------------------------------------------------------------------


def kline_to_bar(kline: list[Any], symbol: str, exchange: str, interval: Interval) -> Bar:
    """Map a Binance kline row to a Bar entity.

    Binance kline positional schema:
      [0]  open time (ms UTC)
      [1]  open price
      [2]  high price
      [3]  low price
      [4]  close price
      [5]  base asset volume
      [6]  close time (ms)
      [7]  quote asset volume
      [8]  number of trades
      [9]  taker buy base volume
      [10] taker buy quote volume
      [11] ignore
    """
    open_time_ms = int(kline[0])
    bar_dt = datetime.fromtimestamp(open_time_ms / 1000, tz=UTC)
    return Bar(
        symbol=symbol.upper(),
        exchange=exchange.upper(),
        interval=interval,
        datetime=bar_dt,
        open=float(kline[1]),
        high=float(kline[2]),
        low=float(kline[3]),
        close=float(kline[4]),
        volume=float(kline[5]),
        tick_count=int(kline[8]),
    )


# ---------------------------------------------------------------------------
# aggTrade frame → quote callback dict
# ---------------------------------------------------------------------------


def aggtrade_to_quote_dict(event: dict[str, Any], symbol: str, exchange: str) -> dict[str, Any]:
    """Map a Binance @aggTrade event to the QuoteAppService callback dict.

    aggTrade frame shape:
      {"e":"aggTrade","E":<event_time_ms>,"s":"BTCUSDT",
       "a":<agg_id>,"p":"16525.50","q":"0.05",
       "f":<first_trade_id>,"l":<last_trade_id>,
       "T":<trade_time_ms>,"m":<is_buyer_maker>,"M":true}

    Contract:
    - timestamp  = T (trade time ms → datetime UTC)
    - last_price = float(p)
    - volume     = float(q)  — per-trade delta, NOT cumulative
    - bid/ask/open_price/high_price/low_price/prev_close/change/change_percent = None
      (@aggTrade does not provide these; downstream handlers tolerate None)
    """
    trade_time_ms = int(event["T"])
    timestamp = datetime.fromtimestamp(trade_time_ms / 1000, tz=UTC)
    symbol_key = f"{exchange.upper()}:{symbol.upper()}"

    return {
        "symbol_key": symbol_key,
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
