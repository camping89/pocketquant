"""Sync symbol command for market data operations."""

from pocketquant.core.common.constants import LIMIT_TVDATAFEED_MAX_BARS
from pocketquant.core.domain.shared.value_objects import Interval
from pydantic import BaseModel, Field


class SyncSymbolCommand(BaseModel):
    """Sync historical OHLCV data for a single symbol."""

    symbol: str = Field(..., description="Trading symbol (e.g., AAPL, BTCUSD)")
    exchange: str = Field(..., description="Exchange name (e.g., NASDAQ, BINANCE)")
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
