"""DTOs for OHLCV operations."""

from dataclasses import dataclass


@dataclass
class OHLCVResult:
    """Result of OHLCV query. ``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
    interval: str
    data: list[dict]
    count: int
