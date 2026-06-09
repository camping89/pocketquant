"""Query object for listing all tracked symbols."""

from pydantic import BaseModel


class ListTrackedSymbolsQuery(BaseModel):
    """List all tracked symbols — no filters (collection is small)."""
