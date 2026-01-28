"""Pure domain service for building bars from ticks."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.domain.shared.value_objects import INTERVAL_SECONDS, Interval


def get_bar_start(timestamp: datetime, interval: Interval) -> datetime:
    """Calculate the aligned bar start time for a given timestamp."""
    seconds = INTERVAL_SECONDS[interval]

    if interval == Interval.DAY_1:
        return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)

    epoch = datetime(1970, 1, 1)
    total_seconds = (timestamp - epoch).total_seconds()
    aligned_seconds = (total_seconds // seconds) * seconds

    return epoch + timedelta(seconds=aligned_seconds)


@dataclass
class BarBuilder:
    """Builds OHLCV bars from incoming ticks. Pure domain logic, no I/O."""

    symbol: str
    exchange: str
    interval: Interval
    bar_start: datetime
    bar_end: datetime | None = None

    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float = 0.0
    tick_count: int = 0

    def __post_init__(self) -> None:
        if self.bar_end is None:
            self.bar_end = self.bar_start + timedelta(
                seconds=INTERVAL_SECONDS[self.interval]
            )

    def add_tick(self, price: float, volume: float | None, timestamp: datetime) -> bool:
        """Add a tick to the bar. Returns False if tick is outside bar range."""
        if timestamp < self.bar_start or timestamp >= self.bar_end:
            return False

        if self.open is None:
            self.open = price

        if self.high is None or price > self.high:
            self.high = price

        if self.low is None or price < self.low:
            self.low = price

        self.close = price

        if volume is not None:
            self.volume += volume

        self.tick_count += 1
        return True

    def is_complete(self, current_time: datetime) -> bool:
        """Check if the bar period has ended."""
        return current_time >= self.bar_end

    def is_empty(self) -> bool:
        """Check if no ticks have been added."""
        return self.tick_count == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "interval": self.interval.value,
            "bar_start": self.bar_start.isoformat(),
            "bar_end": self.bar_end.isoformat() if self.bar_end else None,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_count": self.tick_count,
        }

    @classmethod
    def create_for_tick(
        cls, symbol: str, exchange: str, interval: Interval, timestamp: datetime
    ) -> BarBuilder:
        """Factory to create a bar builder aligned to the tick timestamp."""
        bar_start = get_bar_start(timestamp, interval)
        return cls(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            bar_start=bar_start,
        )
