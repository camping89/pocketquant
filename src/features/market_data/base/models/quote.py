from datetime import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Quote(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    symbol: str = Field(..., description="Trading symbol")
    exchange: str = Field(..., description="Exchange name")
    timestamp: dt = Field(default_factory=dt.utcnow, description="Quote timestamp")

    last_price: float = Field(..., alias="lp", description="Last traded price")
    bid: float | None = Field(None, description="Best bid price")
    ask: float | None = Field(None, description="Best ask price")

    volume: float | None = Field(None, description="Total volume")

    change: float | None = Field(None, alias="ch", description="Price change")
    change_percent: float | None = Field(None, alias="chp", description="Price change percent")

    open_price: float | None = Field(None, description="Session open price")
    high_price: float | None = Field(None, description="Session high price")
    low_price: float | None = Field(None, description="Session low price")
    prev_close: float | None = Field(None, description="Previous close price")

    def to_cache_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "timestamp": self.timestamp.isoformat(),
            "last_price": self.last_price,
            "bid": self.bid,
            "ask": self.ask,
            "volume": self.volume,
            "change": self.change,
            "change_percent": self.change_percent,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "prev_close": self.prev_close,
        }

    @classmethod
    def from_cache_dict(cls, data: dict[str, Any]) -> Quote:
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = dt.fromisoformat(data["timestamp"])
        return cls(**data)


class QuoteSubscription(BaseModel):
    symbol: str = Field(..., description="Trading symbol")
    exchange: str = Field(..., description="Exchange name")

    @property
    def key(self) -> str:
        return f"{self.exchange}:{self.symbol}".upper()


class QuoteTick(BaseModel):
    symbol: str
    exchange: str
    timestamp: dt
    price: float
    volume: float | None = None

    def to_mongo(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol.upper(),
            "exchange": self.exchange.upper(),
            "timestamp": self.timestamp,
            "price": self.price,
            "volume": self.volume,
        }


class AggregatedBar(BaseModel):
    symbol: str
    exchange: str
    interval: str
    bar_start: dt
    bar_end: dt
    open: float
    high: float
    low: float
    close: float
    volume: float
    tick_count: int

    def to_ohlcv_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol.upper(),
            "exchange": self.exchange.upper(),
            "interval": self.interval,
            "datetime": self.bar_start,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }
