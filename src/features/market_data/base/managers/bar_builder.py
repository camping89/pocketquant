"""BarBuilder aggregates ticks into a single OHLCV bar for one interval."""

from datetime import UTC, datetime, timedelta
from typing import Any

from src.features.market_data.base.models.ohlcv import Interval
from src.features.market_data.base.models.quote import AggregatedBar, QuoteTick

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
}


class BarBuilder:
    def __init__(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        bar_start: datetime,
    ):
        self.symbol = symbol
        self.exchange = exchange
        self.interval = interval
        self.bar_start = bar_start
        self.bar_end = bar_start + timedelta(seconds=INTERVAL_SECONDS[interval])

        self.open: float | None = None
        self.high: float | None = None
        self.low: float | None = None
        self.close: float | None = None
        self.volume: float = 0.0
        self.tick_count: int = 0

    def add_tick(self, tick: QuoteTick) -> bool:
        if tick.timestamp < self.bar_start or tick.timestamp >= self.bar_end:
            return False

        price = tick.price

        if self.open is None:
            self.open = price

        if self.high is None or price > self.high:
            self.high = price

        if self.low is None or price < self.low:
            self.low = price

        self.close = price

        if tick.volume:
            self.volume += tick.volume

        self.tick_count += 1

        return True

    def is_complete(self, current_time: datetime) -> bool:
        return current_time >= self.bar_end

    def is_empty(self) -> bool:
        return self.tick_count == 0

    def to_aggregated_bar(self) -> AggregatedBar | None:
        if self.is_empty():
            return None

        # All OHLC values are guaranteed non-None when not empty
        if self.open is None or self.high is None or self.low is None or self.close is None:
            return None

        return AggregatedBar(
            symbol=self.symbol,
            exchange=self.exchange,
            interval=self.interval.value,
            bar_start=self.bar_start,
            bar_end=self.bar_end,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            tick_count=self.tick_count,
        )

    def to_cache_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "interval": self.interval.value,
            "bar_start": self.bar_start.isoformat(),
            "bar_end": self.bar_end.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_count": self.tick_count,
        }


def get_bar_start(timestamp: datetime, interval: Interval) -> datetime:
    """Align timestamp to the start of its bar interval."""
    seconds = INTERVAL_SECONDS[interval]

    if interval == Interval.DAY_1:
        return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)

    # Use timezone-aware epoch if timestamp has timezone
    if timestamp.tzinfo is not None:
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
    else:
        epoch = datetime(1970, 1, 1)

    total_seconds = (timestamp - epoch).total_seconds()
    aligned_seconds = (total_seconds // seconds) * seconds

    return epoch + timedelta(seconds=aligned_seconds)
