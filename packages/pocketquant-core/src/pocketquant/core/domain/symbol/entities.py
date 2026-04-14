"""Symbol entity - Pydantic model with MongoDB persistence."""

from datetime import datetime
from typing import Any

from pocketquant.core.common.time import utc_now
from pocketquant.core.common.uuid import UUID, generate_id
from pydantic import BaseModel, ConfigDict, Field


class Symbol(BaseModel):
    """Tradeable instrument - persisted to MongoDB."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=generate_id)
    code: str = ""
    exchange: str = ""
    name: str | None = None
    asset_type: str | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=utc_now)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Symbol):
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
    ) -> Symbol:
        """Factory method to create a new symbol."""
        return cls(code=code.upper(), exchange=exchange.upper(), name=name, asset_type=asset_type)

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True

    @property
    def symbol_key(self) -> str:
        """Return 'EXCHANGE:CODE' format."""
        return f"{self.exchange}:{self.code}"

    def to_mongo(self) -> dict[str, Any]:
        """Serialize to MongoDB document. 'code' maps to 'symbol' field for backward compat."""
        return {
            "_id": str(self.id),
            "symbol": self.code,  # MongoDB field "symbol" maps from entity field "code"
            "exchange": self.exchange,
            "name": self.name,
            "asset_type": self.asset_type,
            "is_active": self.is_active,
            "created_at": self.created_at,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> Symbol:
        """Reconstruct from MongoDB document."""
        raw_id = doc.get("_id", "")
        return cls(
            id=UUID(str(raw_id)) if raw_id else generate_id(),
            code=doc.get("symbol", ""),
            exchange=doc.get("exchange", ""),
            name=doc.get("name"),
            asset_type=doc.get("asset_type"),
            is_active=doc.get("is_active", True),
            created_at=doc.get("created_at", utc_now()),
        )
