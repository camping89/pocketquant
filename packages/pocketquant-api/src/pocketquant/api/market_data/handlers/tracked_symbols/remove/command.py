"""Command for removing a tracked symbol."""

from pydantic import BaseModel, Field


class RemoveTrackedSymbolCommand(BaseModel):
    """Remove (exchange, symbol) from tracked_symbols."""

    exchange: str = Field(..., description="Exchange of the symbol to remove")
    symbol: str = Field(..., description="Symbol to remove")
