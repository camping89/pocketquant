"""Symbol entity - Pydantic model with MongoDB persistence.

Composite symbol format ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``) is the
single identity field. Exchange is encoded as opaque postfix; business logic
never decomposes it. Decomposition is presentation-layer-only.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pocketquant.core.common.time import utc_now
from pocketquant.core.common.uuid import UUID, generate_id
from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.domain.symbol.value_objects import (
    CALENDAR_CRYPTO_24_7,
    DEFAULT_CALENDAR_BY_ASSET_CLASS,
    LINEAR_SPEC,
    ContractSpec,
)

COMPOSITE_SYMBOL_RE = re.compile(r"^[A-Z0-9_!-]+:[A-Z0-9_-]+$")

# Stricter validation pattern for API path/body input: each segment allows dot,
# bounded to 32 chars. Shared by the HTTP route validator and the tracked-symbol
# command validators so both reject the same shapes.
COMPOSITE_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9._!-]{1,32}:[A-Z0-9._-]{1,32}$")


class Symbol(BaseModel):
    """Tradeable instrument - persisted to MongoDB.

    ``symbol`` stores composite identifier ``{code}:{exchange}``.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=generate_id)
    symbol: str = ""
    name: str | None = None
    asset_class: AssetClass = AssetClass.CRYPTO_SPOT
    calendar_id: str = CALENDAR_CRYPTO_24_7
    contract_spec: ContractSpec = LINEAR_SPEC
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
        asset_class: AssetClass = AssetClass.CRYPTO_SPOT,
        calendar_id: str | None = None,
        contract_spec: ContractSpec | None = None,
    ) -> Symbol:
        """Create a symbol, deriving its calendar from its asset class.

        ``calendar_id`` is derived rather than defaulted so the two fields cannot
        silently disagree. An explicit value still wins, for a venue that needs a
        non-default calendar for the same asset class.
        """
        return cls(
            symbol=symbol.upper(),
            name=name,
            asset_class=asset_class,
            calendar_id=calendar_id or DEFAULT_CALENDAR_BY_ASSET_CLASS[asset_class],
            contract_spec=contract_spec or LINEAR_SPEC,
        )

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
            "asset_class": self.asset_class.value,
            "calendar_id": self.calendar_id,
            "contract_spec": self.contract_spec.to_mongo(),
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
            asset_class=AssetClass(doc.get("asset_class", AssetClass.CRYPTO_SPOT.value)),
            calendar_id=doc.get("calendar_id", CALENDAR_CRYPTO_24_7),
            contract_spec=ContractSpec.from_mongo(doc.get("contract_spec")),
            is_active=doc.get("is_active", True),
            created_at=doc.get("created_at", utc_now()),
        )
