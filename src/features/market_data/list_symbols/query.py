"""Query for listing symbols."""

from pydantic import BaseModel, Field


class ListSymbolsQuery(BaseModel):
    """Query to list symbols, optionally filtered by exchange."""

    exchange: str | None = Field(default=None, description="Filter by exchange")
