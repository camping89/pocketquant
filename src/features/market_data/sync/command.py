"""Sync commands for market data operations."""

from dataclasses import dataclass


@dataclass
class SyncSymbolCommand:
    """Sync historical OHLCV data for a single symbol."""

    symbol: str
    exchange: str
    interval: str = "1d"
    n_bars: int = 500
    background: bool = False


@dataclass
class BulkSyncCommand:
    """Sync multiple symbols in sequence."""

    symbols: list[dict]
    interval: str = "1d"
    n_bars: int = 500
