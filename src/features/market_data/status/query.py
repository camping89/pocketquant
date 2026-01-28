"""Status queries."""

from dataclasses import dataclass


@dataclass
class GetSyncStatusQuery:
    """Query to get all sync statuses."""

    pass


@dataclass
class GetSymbolSyncStatusQuery:
    """Query to get sync status for a specific symbol."""

    symbol: str
    exchange: str
    interval: str = "1d"


@dataclass
class GetQuoteServiceStatusQuery:
    """Query to get quote service status."""

    pass
