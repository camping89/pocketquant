"""Symbol aggregate root — Pydantic model with MongoDB persistence."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from src.common.uuid import UUID, generate_id
from src.domain.shared.domain_event import DomainEvent
from src.domain.symbol.value_objects import SymbolInfo


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SymbolAggregate(BaseModel):
    """Aggregate root for symbol management."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=generate_id)
    info: SymbolInfo | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SymbolAggregate):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    @classmethod
    def create(
        cls,
        code: str,
        exchange: str,
        name: str | None = None,
        asset_type: str | None = None,
    ) -> SymbolAggregate:
        """Factory method to create a new symbol aggregate."""
        info = SymbolInfo(
            code=code.upper(),
            exchange=exchange.upper(),
            name=name,
            asset_type=asset_type,
        )
        return cls(info=info)

    def deactivate(self) -> None:
        """Deactivate the symbol."""
        if self.info:
            self.info = replace(self.info, is_active=False)

    def activate(self) -> None:
        """Activate the symbol."""
        if self.info:
            self.info = replace(self.info, is_active=True)

    # -- Convenience properties for flat access --

    @property
    def symbol(self) -> str:
        return self.info.code if self.info else ""

    @property
    def exchange(self) -> str:
        return self.info.exchange if self.info else ""

    @property
    def name(self) -> str | None:
        return self.info.name if self.info else None

    @property
    def asset_type(self) -> str | None:
        return self.info.asset_type if self.info else None

    @property
    def is_active(self) -> bool:
        return self.info.is_active if self.info else True

    def to_mongo(self) -> dict[str, Any]:
        """Serialize to MongoDB document."""
        return {
            "_id": str(self.id),
            "symbol": self.info.code.upper() if self.info else "",
            "exchange": self.info.exchange.upper() if self.info else "",
            "name": self.info.name if self.info else None,
            "asset_type": self.info.asset_type if self.info else None,
            "is_active": self.info.is_active if self.info else True,
            "created_at": self.created_at,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> SymbolAggregate:
        """Reconstruct from MongoDB document."""
        info = SymbolInfo(
            code=doc.get("symbol", ""),
            exchange=doc.get("exchange", ""),
            name=doc.get("name"),
            asset_type=doc.get("asset_type"),
            is_active=doc.get("is_active", True),
        )
        raw_id = doc.get("_id", "")
        return cls(
            id=UUID(str(raw_id)) if raw_id else generate_id(),
            info=info,
            created_at=doc.get("created_at", _utc_now()),
        )

    def get_uncommitted_events(self) -> list[DomainEvent]:
        return self._events.copy()

    def clear_events(self) -> None:
        self._events.clear()
