"""Query to get the latest quote for a specific symbol."""

from pydantic import BaseModel


class GetLatestQuoteQuery(BaseModel):
    """Get the latest quote for a specific symbol."""

    symbol: str
    exchange: str
