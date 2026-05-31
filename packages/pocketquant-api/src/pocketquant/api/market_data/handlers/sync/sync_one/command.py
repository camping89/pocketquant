"""Sync symbol command for market data operations."""

from pocketquant.core.common.constants import LIMIT_TVDATAFEED_MAX_BARS
from pocketquant.core.domain.shared.enums import Interval
from pydantic import BaseModel, Field


class SyncSymbolCommand(BaseModel):
    """Sync historical OHLCV data for a single composite symbol.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    symbol: str = Field(..., description="Composite symbol (e.g., BTCUSDT:BINANCE)")
    interval: Interval = Field(default=Interval.DAY_1, description="Time interval")
    n_bars: int = Field(
        default=LIMIT_TVDATAFEED_MAX_BARS,
        ge=1,
        le=LIMIT_TVDATAFEED_MAX_BARS,
        description="Number of bars to fetch",
    )
    skip_filter: bool = Field(
        default=False,
        description="Bypass _filter_new_bars — used by repair to fill gaps",
    )
    source: str = Field(
        ...,
        description="Audit label identifying write path (rest_sync_1m, rest_backfill, ...).",
    )
