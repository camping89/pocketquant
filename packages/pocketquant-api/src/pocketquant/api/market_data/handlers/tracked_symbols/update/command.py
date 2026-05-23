"""Command for updating a tracked symbol's metadata."""

from pydantic import BaseModel, Field


class UpdateTrackedSymbolCommand(BaseModel):
    """Update metadata on an existing composite symbol. Future-proof placeholder."""

    symbol: str = Field(..., description="Composite symbol to update, e.g. BTCUSDT:BINANCE")
    # Extensible: add metadata fields here as requirements evolve (e.g. alias, tags)
