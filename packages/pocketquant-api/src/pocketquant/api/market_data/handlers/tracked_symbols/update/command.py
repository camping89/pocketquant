"""Command for updating a tracked symbol's metadata."""

from pydantic import BaseModel, Field


class UpdateTrackedSymbolCommand(BaseModel):
    """Update metadata on an existing (exchange, symbol). Future-proof placeholder."""

    exchange: str = Field(..., description="Exchange of the symbol to update")
    symbol: str = Field(..., description="Symbol to update")
    # Extensible: add metadata fields here as requirements evolve (e.g. alias, tags)
