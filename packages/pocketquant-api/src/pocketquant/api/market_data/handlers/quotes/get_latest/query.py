"""Query to get the latest quote for a specific composite symbol."""

from pydantic import BaseModel


class GetLatestQuoteQuery(BaseModel):
    """Get the latest quote. ``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
