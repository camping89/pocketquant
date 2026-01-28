from datetime import datetime as dt
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Interval(str, Enum):
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


class OHLCVBase(BaseModel):
    symbol: str = Field(..., description="Trading symbol (e.g., AAPL, BTCUSD)")
    exchange: str = Field(..., description="Exchange name (e.g., NASDAQ, BINANCE)")
    interval: Interval = Field(..., description="Time interval")
    datetime: dt = Field(..., description="Bar datetime (UTC)")
    open: float = Field(..., description="Open price")
    high: float = Field(..., description="High price")
    low: float = Field(..., description="Low price")
    close: float = Field(..., description="Close price")
    volume: float = Field(..., description="Trading volume")


class OHLCVCreate(OHLCVBase):
    pass


class OHLCV(OHLCVBase):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(None, alias="_id")
    created_at: dt = Field(default_factory=dt.utcnow)

    def to_mongo(self) -> dict[str, Any]:
        data = self.model_dump(exclude={"id"})
        data["interval"] = self.interval.value
        return data

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> OHLCV:
        doc["_id"] = str(doc.get("_id", ""))
        if isinstance(doc.get("interval"), str):
            doc["interval"] = Interval(doc["interval"])
        return cls(**doc)


class OHLCVResponse(BaseModel):
    symbol: str
    exchange: str
    interval: str
    data: list[dict[str, Any]]
    count: int


class SyncStatus(BaseModel):
    symbol: str
    exchange: str
    interval: str
    last_sync_at: dt | None = None
    last_bar_at: dt | None = None
    bar_count: int = 0
    status: str = "pending"
    error_message: str | None = None

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> SyncStatus:
        doc.pop("_id", None)
        return cls(**doc)
