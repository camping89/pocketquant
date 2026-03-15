"""Bar entities — Pydantic models with MongoDB persistence."""

from datetime import UTC
from datetime import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.common.uuid import UUID, generate_id
from src.domain.shared.enums import Interval


def _utc_now() -> dt:
    return dt.now(UTC)


class Bar(BaseModel):
    """Price bar with identity and MongoDB persistence.

    Flat structure for direct field access. Used by repositories,
    handlers, and backtesting engine.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=generate_id)
    symbol: str = ""
    exchange: str = ""
    interval: Interval | None = None
    datetime: dt | None = None
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    tick_count: int = 0
    created_at: dt = Field(default_factory=_utc_now)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Bar):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def is_complete(self) -> bool:
        return self.tick_count > 0

    def to_mongo(self) -> dict[str, Any]:
        """Serialize to MongoDB document."""
        return {
            "_id": str(self.id),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "interval": self.interval.value if self.interval else None,
            "datetime": self.datetime,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_count": self.tick_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> Bar:
        """Reconstruct from MongoDB document."""
        raw_id = doc.get("_id", "")
        interval_val = doc.get("interval")
        if isinstance(interval_val, str):
            interval_val = Interval(interval_val)
        return cls(
            id=UUID(str(raw_id)) if raw_id else generate_id(),
            symbol=doc.get("symbol", ""),
            exchange=doc.get("exchange", ""),
            interval=interval_val,
            datetime=doc.get("datetime"),
            open=doc.get("open", 0.0),
            high=doc.get("high", 0.0),
            low=doc.get("low", 0.0),
            close=doc.get("close", 0.0),
            volume=doc.get("volume", 0.0),
            tick_count=doc.get("tick_count", 0),
            created_at=doc.get("created_at", _utc_now()),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for API serialization."""
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "interval": self.interval.value if self.interval else None,
            "datetime": self.datetime.isoformat() if self.datetime else None,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_count": self.tick_count,
        }
