"""DTOs for OHLCV operations."""

from dataclasses import dataclass


@dataclass
class OHLCVResult:
    """Result of OHLCV query."""

    symbol: str
    exchange: str
    interval: str
    data: list[dict]
    count: int
