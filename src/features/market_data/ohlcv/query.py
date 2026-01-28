"""OHLCV queries."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class GetOHLCVQuery:
    """Query to retrieve OHLCV bars for a symbol."""

    symbol: str
    exchange: str
    interval: str = "1d"
    limit: int = 1000
    start_date: datetime | None = None
    end_date: datetime | None = None
