from datetime import UTC
from datetime import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.common.uuid import generate_id_str
from src.domain.shared.value_objects import Interval


def _utc_now() -> dt:
    return dt.now(UTC)


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


class OHLCV(OHLCVBase):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(None, alias="_id")
    created_at: dt = Field(default_factory=_utc_now)

    def to_mongo(self) -> dict[str, Any]:
        data = self.model_dump(exclude={"id"})
        data["interval"] = self.interval.value
        if self.id is None:
            data["_id"] = generate_id_str()
        else:
            data["_id"] = self.id
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
