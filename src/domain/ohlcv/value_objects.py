"""OHLCV value objects."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from src.domain.shared.value_objects import Interval


class OHLCV(BaseModel):
    """Immutable OHLCV price bar data."""

    model_config = ConfigDict(frozen=True)

    open: float
    high: float
    low: float
    close: float
    volume: float

    @model_validator(mode="after")
    def validate_ohlcv(self) -> OHLCV:
        if self.high < self.low:
            raise ValueError("High must be >= Low")
        if self.open < self.low or self.open > self.high:
            raise ValueError("Open must be between Low and High")
        if self.close < self.low or self.close > self.high:
            raise ValueError("Close must be between Low and High")
        if self.volume < 0:
            raise ValueError("Volume must be non-negative")
        return self


class BarRange(BaseModel):
    """Time range for a bar."""

    model_config = ConfigDict(frozen=True)

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_range(self) -> BarRange:
        if self.end <= self.start:
            raise ValueError("End must be after start")
        return self

    def contains(self, timestamp: datetime) -> bool:
        """Check if timestamp falls within this bar range."""
        return self.start <= timestamp < self.end

    @property
    def duration_seconds(self) -> int:
        return int((self.end - self.start).total_seconds())


INTERVAL_TO_TVDATAFEED = {
    Interval.MINUTE_1: "in_1_minute",
    Interval.MINUTE_3: "in_3_minute",
    Interval.MINUTE_5: "in_5_minute",
    Interval.MINUTE_15: "in_15_minute",
    Interval.MINUTE_30: "in_30_minute",
    Interval.MINUTE_45: "in_45_minute",
    Interval.HOUR_1: "in_1_hour",
    Interval.HOUR_2: "in_2_hour",
    Interval.HOUR_3: "in_3_hour",
    Interval.HOUR_4: "in_4_hour",
    Interval.DAY_1: "in_daily",
    Interval.WEEK_1: "in_weekly",
    Interval.MONTH_1: "in_monthly",
}
