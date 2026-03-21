"""SyncStatus entity — Pydantic model with MongoDB persistence."""

from datetime import datetime as dt
from typing import Any

from pocketquant.core.common.uuid import UUID, generate_id
from pydantic import BaseModel, Field


class SyncStatus(BaseModel):
    """Tracks data sync status for a symbol/exchange/interval."""

    id: UUID = Field(default_factory=generate_id)
    symbol: str = ""
    exchange: str = ""
    interval: str = ""
    status: str = "pending"
    last_sync_at: dt | None = None
    last_bar_at: dt | None = None
    bar_count: int = 0
    error_message: str | None = None

    def to_mongo(self) -> dict[str, Any]:
        """Serialize to MongoDB document."""
        return {
            "_id": str(self.id),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "interval": self.interval,
            "status": self.status,
            "last_sync_at": self.last_sync_at,
            "last_bar_at": self.last_bar_at,
            "bar_count": self.bar_count,
            "error_message": self.error_message,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> SyncStatus:
        """Reconstruct from MongoDB document."""
        raw_id = doc.get("_id", "")
        return cls(
            id=UUID(str(raw_id)) if raw_id else generate_id(),
            symbol=doc.get("symbol", ""),
            exchange=doc.get("exchange", ""),
            interval=doc.get("interval", ""),
            status=doc.get("status", "pending"),
            last_sync_at=doc.get("last_sync_at"),
            last_bar_at=doc.get("last_bar_at"),
            bar_count=doc.get("bar_count", 0),
            error_message=doc.get("error_message"),
        )
