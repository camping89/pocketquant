"""TrackedSymbol entity — represents a symbol eligible for live data pipelines.

``symbol`` is the composite identifier ``{code}:{exchange}``.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pocketquant.core.common.time import utc_now
from pocketquant.core.common.uuid import UUID, generate_id


class TrackedSymbol(BaseModel):
    """A symbol registered for WS subscription and cron sync.

    Uniqueness enforced at the DB layer via unique index on composite ``symbol``.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=generate_id)
    symbol: str
    created_at: datetime = Field(default_factory=utc_now)
    seeded_from: str | None = None  # 'auto-seed' | 'admin' | None

    def to_mongo(self) -> dict[str, Any]:
        """Serialize to MongoDB document."""
        return {
            "_id": str(self.id),
            "symbol": self.symbol,
            "created_at": self.created_at,
            "seeded_from": self.seeded_from,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> TrackedSymbol:
        """Reconstruct from MongoDB document."""
        raw_id = doc.get("_id", "")
        try:
            parsed_id = UUID(str(raw_id))
        except ValueError:
            # Legacy doc keyed by composite symbol — boot migration re-keys it.
            parsed_id = generate_id()
        return cls(
            id=parsed_id,
            symbol=doc["symbol"],
            created_at=doc.get("created_at") or utc_now(),
            seeded_from=doc.get("seeded_from"),
        )
