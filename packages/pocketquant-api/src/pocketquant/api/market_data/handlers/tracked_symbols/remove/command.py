"""Command for removing a tracked symbol."""

from pydantic import BaseModel, Field


class RemoveTrackedSymbolCommand(BaseModel):
    """Remove composite symbol from tracked_symbols."""

    symbol: str = Field(..., description="Composite symbol to remove, e.g. BTCUSDT:BINANCE")
