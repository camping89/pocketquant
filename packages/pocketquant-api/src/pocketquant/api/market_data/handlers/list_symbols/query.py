"""Query for listing symbols."""

from pydantic import BaseModel


class ListSymbolsQuery(BaseModel):
    """Query to list all known symbols."""

    pass
