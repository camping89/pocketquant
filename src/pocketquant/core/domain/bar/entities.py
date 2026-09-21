"""Bar entities — Pydantic models with MongoDB persistence."""

from datetime import UTC, date
from datetime import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pocketquant.core.common.time import coerce_utc, to_utc_iso, utc_now
from pocketquant.core.common.uuid import UUID, generate_id
from pocketquant.core.domain.shared.enums import Interval

# Source labels — identify which write path produced/updated a bar.
# KISS: str literals, no Enum. Use constants for refactor safety.
SOURCE_REST_SYNC_1M = "rest_sync_1m"
SOURCE_REST_BACKFILL = "rest_backfill"
SOURCE_REST_REPAIR = "rest_repair"
SOURCE_CASCADE = "cascade"
SOURCE_TRACKED_SYMBOL_BACKFILL = "tracked_symbol_backfill"
SOURCE_BULK_SYNC = "bulk_sync_api"
SOURCE_ONE_TIME_LEGACY = "one_time_legacy"


class Bar(BaseModel):
    """Price bar with identity and MongoDB persistence.

    Flat structure for direct field access. ``symbol`` stores composite
    identifier ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=generate_id)
    symbol: str = ""
    interval: Interval | None = None
    datetime: dt | None = None
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    tick_count: int = 0
    # Session-day key and its calendar. `datetime` still moves with DST, so a
    # consumer that wants "which trading day is this" needs a stable key that
    # does not. Populated at the write path from Phase 3; None on crypto bars
    # written before that.
    session_date: date | None = None
    calendar_id: str | None = None
    created_at: dt = Field(default_factory=utc_now)
    # Audit fields — repository is single writer. Entity treats them as read-only:
    # populated by from_mongo(), NOT serialized by to_mongo() (BarRepository writes via $set).
    updated_at: dt | None = None
    source: str | None = None

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
            "interval": self.interval.value if self.interval else None,
            "datetime": self.datetime,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_count": self.tick_count,
            # ISO string, not a BSON date: a session day is a calendar key, and
            # storing it as an instant invites it being read as one.
            "session_date": self.session_date.isoformat() if self.session_date else None,
            "calendar_id": self.calendar_id,
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
            interval=interval_val,
            datetime=coerce_utc(doc.get("datetime")),
            open=doc.get("open", 0.0),
            high=doc.get("high", 0.0),
            low=doc.get("low", 0.0),
            close=doc.get("close", 0.0),
            volume=doc.get("volume", 0.0),
            tick_count=doc.get("tick_count", 0),
            session_date=(
                date.fromisoformat(raw_session_date)
                if isinstance(raw_session_date := doc.get("session_date"), str)
                else None
            ),
            calendar_id=doc.get("calendar_id"),
            created_at=coerce_utc(doc.get("created_at")) or utc_now(),
            updated_at=coerce_utc(doc.get("updated_at")),
            source=doc.get("source"),
        )

    @field_validator("datetime", "created_at", "updated_at", mode="after")
    @classmethod
    def _require_utc(cls, v: dt | None) -> dt | None:
        """Reject naive datetimes at the domain boundary.

        A naive value here means an adapter guessed a zone, or failed to. Both
        produce bars that look right on one host and wrong on every other.
        """
        if v is None:
            return v
        if v.tzinfo is None:
            raise ValueError(
                "Bar datetimes must be timezone-aware; adapters must emit UTC instants"
            )
        return v.astimezone(UTC)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "interval": self.interval.value if self.interval else None,
            "datetime": to_utc_iso(self.datetime),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_count": self.tick_count,
            "updated_at": to_utc_iso(self.updated_at),
            "source": self.source,
        }
