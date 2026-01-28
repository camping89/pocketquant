"""OHLCV value objects."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OHLCV:
    """Immutable OHLCV price bar data."""

    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError("High must be >= Low")
        if self.open < self.low or self.open > self.high:
            raise ValueError("Open must be between Low and High")
        if self.close < self.low or self.close > self.high:
            raise ValueError("Close must be between Low and High")
        if self.volume < 0:
            raise ValueError("Volume must be non-negative")


@dataclass(frozen=True)
class BarRange:
    """Time range for a bar."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("End must be after start")

    def contains(self, timestamp: datetime) -> bool:
        """Check if timestamp falls within this bar range."""
        return self.start <= timestamp < self.end

    @property
    def duration_seconds(self) -> int:
        return int((self.end - self.start).total_seconds())
