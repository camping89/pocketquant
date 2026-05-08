"""TrackedSymbol entity — represents a symbol eligible for live data pipelines."""

from datetime import datetime
from typing import Any

from pocketquant.core.common.time import utc_now
from pydantic import BaseModel, ConfigDict, Field


class TrackedSymbol(BaseModel):
    """A (exchange, symbol) pair registered for WS subscription and cron sync.

    Uniqueness enforced at the DB layer via compound index on (exchange, symbol).
    """

    model_config = ConfigDict(populate_by_name=True)

    exchange: str
    symbol: str
    created_at: datetime = Field(default_factory=utc_now)
    seeded_from: str | None = None  # 'auto-seed' | 'admin' | None

    def to_mongo(self) -> dict[str, Any]:
        """Serialize to MongoDB document. Uses (exchange, symbol) as natural _id."""
        return {
            "_id": f"{self.exchange}:{self.symbol}",
            "exchange": self.exchange,
            "symbol": self.symbol,
            "created_at": self.created_at,
            "seeded_from": self.seeded_from,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> TrackedSymbol:
        """Reconstruct from MongoDB document."""
        return cls(
            exchange=doc["exchange"],
            symbol=doc["symbol"],
            created_at=doc.get("created_at") or utc_now(),
            seeded_from=doc.get("seeded_from"),
        )
