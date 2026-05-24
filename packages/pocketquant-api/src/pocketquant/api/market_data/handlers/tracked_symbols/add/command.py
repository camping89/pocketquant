"""Command for adding a tracked symbol."""

from pocketquant.api.common.symbol_validation import COMPOSITE_SYMBOL_PATTERN
from pydantic import BaseModel, Field, field_validator


class AddTrackedSymbolCommand(BaseModel):
    """Add composite ``{code}:{exchange}`` symbol to tracked_symbols. Idempotent — 200 if exists."""

    symbol: str = Field(
        ...,
        min_length=3,
        max_length=65,
        description="Composite symbol e.g. BTCUSDT:BINANCE",
    )

    @field_validator("symbol", mode="before")
    @classmethod
    def upper_and_validate(cls, v: str) -> str:
        v = v.strip().upper()
        if not COMPOSITE_SYMBOL_PATTERN.match(v):
            raise ValueError("Must be composite {CODE}:{EXCHANGE} format")
        return v
