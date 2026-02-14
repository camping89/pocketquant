"""Sync symbol command for market data operations."""

from pydantic import BaseModel, Field

from src.common.constants import LIMIT_TVDATAFEED_MAX_BARS
from src.domain.shared.value_objects import Interval


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
