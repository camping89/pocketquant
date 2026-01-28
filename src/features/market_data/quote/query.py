"""Quote queries."""

from dataclasses import dataclass


@dataclass
class GetLatestQuoteQuery:
    """Query to get the latest quote for a symbol."""

    symbol: str
    exchange: str


@dataclass
class GetAllQuotesQuery:
    """Query to get all active quotes."""

    pass
