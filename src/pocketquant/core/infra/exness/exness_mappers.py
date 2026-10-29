from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval

INTERVAL_TO_EXNESS: dict[Interval, str] = {
    Interval.MINUTE_1: "M1",
    Interval.MINUTE_5: "M5",
    Interval.MINUTE_15: "M15",
    Interval.HOUR_1: "H1",
    Interval.HOUR_4: "H4",
    Interval.DAY_1: "D1",
    Interval.WEEK_1: "W1",
}

# Keyed by the full composite symbol. The spike recorded that the account's
# instrument names equal the codes, with no suffix.
EXNESS_INSTRUMENTS: dict[str, str] = {
    "XAUUSD:EXNESS": "XAUUSD",
    "EURUSD:EXNESS": "EURUSD",
    "BTCUSD:EXNESS": "BTCUSD",
}


def instrument_name(symbol: str) -> str | None:
    return EXNESS_INSTRUMENTS.get(symbol.upper())


def composite_for(instrument: str) -> str | None:
    return next((k for k, v in EXNESS_INSTRUMENTS.items() if v == instrument), None)


# Exness volume is a tick count, so it fills both volume and tick_count.
def candle_to_bar(candle: dict[str, Any], symbol: str, interval: Interval) -> Bar:
    return Bar(
        symbol=symbol.upper(),
        interval=interval,
        datetime=datetime.fromisoformat(candle["time"]).astimezone(UTC),
        open=float(candle["open"]),
        high=float(candle["high"]),
        low=float(candle["low"]),
        close=float(candle["close"]),
        volume=float(candle["volume"]),
        tick_count=int(candle["volume"]),
    )


# The last price is the bid.
def tick_to_quote_dict(tick: dict[str, Any], symbol: str) -> dict[str, Any]:
    bid = float(tick["bid"])
    return {
        "symbol": symbol.upper(),
        "timestamp": datetime.fromisoformat(tick["timestamp"]).astimezone(UTC),
        "last_price": bid,
        "volume": None,
        "bid": bid,
        "ask": float(tick["ask"]),
        "change": None,
        "change_percent": None,
        "open_price": None,
        "high_price": None,
        "low_price": None,
        "prev_close": None,
    }


# Floored to the lot step; None below the minimum lot. Without max_lots the cap is the
# minimum lot.
def units_to_lots(
    quantity: Decimal,
    *,
    contract_size: Decimal,
    volume_min: Decimal,
    volume_step: Decimal,
    volume_max: Decimal,
    max_lots: Decimal | None,
) -> Decimal | None:
    raw = quantity / contract_size
    if raw < volume_min:
        return None
    cap = min(volume_max, max_lots if max_lots is not None else volume_min)
    steps = ((min(raw, cap) - volume_min) / volume_step).to_integral_value(rounding=ROUND_FLOOR)
    return volume_min + steps * volume_step


def lots_to_units(lots: Decimal, contract_size: Decimal) -> float:
    return float(lots * contract_size)


def format_price(price: float, point_digits: int) -> str:
    return f"{price:.{point_digits}f}"
