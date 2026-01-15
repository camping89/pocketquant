"""Symbol metadata models."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """Return current UTC datetime with timezone info."""
    return datetime.now(UTC)


class SymbolBase(BaseModel):
    """Base symbol model."""

    symbol: str = Field(..., description="Trading symbol")
    exchange: str = Field(..., description="Exchange name")
    name: str | None = Field(None, description="Full name/description")
    asset_type: str | None = Field(None, description="Asset type (stock, crypto, forex, etc)")
    currency: str | None = Field(None, description="Quote currency")
    is_active: bool = Field(default=True, description="Whether symbol is actively traded")


class SymbolCreate(SymbolBase):
    """Model for creating symbol records."""

    pass


class Symbol(SymbolBase):
    """Full symbol model with database fields."""

    id: str | None = Field(None, alias="_id")
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    class Config:
        populate_by_name = True

    def to_mongo(self) -> dict[str, Any]:
        """Convert to MongoDB document format."""
        return self.model_dump(exclude={"id"})

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> Symbol:
        """Create instance from MongoDB document."""
        doc["_id"] = str(doc.get("_id", ""))
        return cls(**doc)
