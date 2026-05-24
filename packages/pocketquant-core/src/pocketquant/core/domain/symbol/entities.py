"""Symbol entity - Pydantic model with MongoDB persistence.

Composite symbol format ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``) is the
single identity field. Exchange is encoded as opaque postfix; business logic
never decomposes it. Decomposition is presentation-layer-only.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pocketquant.core.common.time import utc_now
from pocketquant.core.common.uuid import UUID, generate_id
from pydantic import BaseModel, ConfigDict, Field, field_validator

COMPOSITE_SYMBOL_RE = re.compile(r"^[A-Z0-9_-]+:[A-Z0-9_-]+$")


class Symbol(BaseModel):
    """Tradeable instrument - persisted to MongoDB.

    ``symbol`` stores composite identifier ``{code}:{exchange}``.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=generate_id)
    symbol: str = ""
    name: str | None = None
    asset_type: str | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        if v == "":
            return v
        up = v.upper()
        if not COMPOSITE_SYMBOL_RE.match(up):
            raise ValueError(
                f"Invalid composite symbol {v!r}; expected format '{{CODE}}:{{EXCHANGE}}'"
            )
        return up

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Symbol):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    @classmethod
    def create(
        cls,
        symbol: str,
        name: str | None = None,
        asset_type: str | None = None,
    ) -> Symbol:
        """Factory method to create a new symbol from composite identifier."""
        return cls(symbol=symbol.upper(), name=name, asset_type=asset_type)

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True

    def to_mongo(self) -> dict[str, Any]:
        """Serialize to MongoDB document."""
        return {
            "_id": str(self.id),
            "symbol": self.symbol,
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
            symbol=doc.get("symbol", ""),
            name=doc.get("name"),
            asset_type=doc.get("asset_type"),
            is_active=doc.get("is_active", True),
            created_at=doc.get("created_at", utc_now()),
        )
