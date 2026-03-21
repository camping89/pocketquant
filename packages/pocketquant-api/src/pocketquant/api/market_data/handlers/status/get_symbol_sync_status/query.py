"""Get symbol sync status query."""

from dataclasses import dataclass


@dataclass
class GetSymbolSyncStatusQuery:
    """Query to get sync status for a specific symbol."""

    symbol: str
    exchange: str
    interval: str = "1d"
