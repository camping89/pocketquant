"""Command for adding a tracked symbol."""

import re

from pydantic import BaseModel, Field, field_validator

_SYMBOL_RE = re.compile(r"^[A-Z0-9._-]+$")


class AddTrackedSymbolCommand(BaseModel):
    """Add (exchange, symbol) to tracked_symbols. Idempotent — 200 if exists."""

    exchange: str = Field(..., min_length=1, max_length=32, description="Exchange name e.g. NASDAQ")
    symbol: str = Field(..., min_length=1, max_length=32, description="Symbol e.g. AAPL")

    @field_validator("exchange", "symbol", mode="before")
    @classmethod
    def upper_and_validate(cls, v: str) -> str:
        v = v.strip().upper()
        if not _SYMBOL_RE.match(v):
            raise ValueError("Must match ^[A-Z0-9._-]+$")
        return v
