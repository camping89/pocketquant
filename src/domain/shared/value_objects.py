"""Shared value objects for the domain layer."""

from dataclasses import dataclass
from enum import Enum


class Interval(str, Enum):
    """Time interval for OHLCV bars."""

    MINUTE_1 = "1m"
    MINUTE_3 = "3m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    MINUTE_45 = "45m"
    HOUR_1 = "1h"
    HOUR_2 = "2h"
    HOUR_3 = "3h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"


@dataclass(frozen=True)
class Symbol:
    """Value object representing a tradeable symbol."""

    code: str
    exchange: str

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("Symbol code is required")
        if not self.exchange:
            raise ValueError("Exchange is required")

    def __str__(self) -> str:
        return f"{self.exchange}:{self.code}"

    @classmethod
    def from_string(cls, symbol_key: str) -> Symbol:
        """Parse 'EXCHANGE:SYMBOL' format."""
        if ":" not in symbol_key:
            raise ValueError(f"Invalid symbol format: {symbol_key}")
        exchange, code = symbol_key.split(":", 1)
        return cls(code=code.upper(), exchange=exchange.upper())


INTERVAL_SECONDS = {
    Interval.MINUTE_1: 60,
    Interval.MINUTE_3: 180,
    Interval.MINUTE_5: 300,
    Interval.MINUTE_15: 900,
    Interval.MINUTE_30: 1800,
    Interval.MINUTE_45: 2700,
    Interval.HOUR_1: 3600,
    Interval.HOUR_2: 7200,
    Interval.HOUR_3: 10800,
    Interval.HOUR_4: 14400,
    Interval.DAY_1: 86400,
    Interval.WEEK_1: 604800,
    Interval.MONTH_1: 2592000,
}
