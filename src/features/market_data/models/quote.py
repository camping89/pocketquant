"""Quote (tick) data models for real-time market data."""

from datetime import datetime as dt
from typing import Any

from pydantic import BaseModel, Field


class Quote(BaseModel):
    """Real-time quote/tick data from market."""

    symbol: str = Field(..., description="Trading symbol")
    exchange: str = Field(..., description="Exchange name")
    timestamp: dt = Field(default_factory=dt.utcnow, description="Quote timestamp")

    # Price data
    last_price: float = Field(..., alias="lp", description="Last traded price")
    bid: float | None = Field(None, description="Best bid price")
    ask: float | None = Field(None, description="Best ask price")

    # Volume
    volume: float | None = Field(None, description="Total volume")

    # Change
    change: float | None = Field(None, alias="ch", description="Price change")
    change_percent: float | None = Field(None, alias="chp", description="Price change percent")

    # Session prices
    open_price: float | None = Field(None, description="Session open price")
    high_price: float | None = Field(None, description="Session high price")
    low_price: float | None = Field(None, description="Session low price")
    prev_close: float | None = Field(None, description="Previous close price")

    class Config:
        populate_by_name = True

    def to_cache_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Redis cache."""
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
    def from_cache_dict(cls, data: dict[str, Any]) -> "Quote":
        """Create from Redis cache dictionary."""
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = dt.fromisoformat(data["timestamp"])
        return cls(**data)


class QuoteSubscription(BaseModel):
    """Subscription request for real-time quotes."""

    symbol: str = Field(..., description="Trading symbol")
    exchange: str = Field(..., description="Exchange name")

    @property
    def key(self) -> str:
        """Unique key for this subscription."""
        return f"{self.exchange}:{self.symbol}".upper()


class QuoteTick(BaseModel):
    """Raw tick data for aggregation into OHLCV bars."""

    symbol: str
    exchange: str
    timestamp: dt
    price: float
    volume: float | None = None

    def to_mongo(self) -> dict[str, Any]:
        """Convert to MongoDB document."""
        return {
            "symbol": self.symbol.upper(),
            "exchange": self.exchange.upper(),
            "timestamp": self.timestamp,
            "price": self.price,
            "volume": self.volume,
        }


class AggregatedBar(BaseModel):
    """Aggregated OHLCV bar from ticks."""

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
        """Convert to OHLCV format for storage."""
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
