"""Bulk sync command for market data operations."""

from pocketquant.core.common.constants import LIMIT_TVDATAFEED_MAX_BARS
from pocketquant.core.domain.shared.value_objects import Interval
from pydantic import BaseModel, Field


class BulkSyncCommand(BaseModel):
    """Sync multiple symbols in sequence."""

    symbols: list[dict] = Field(
        ...,
        description="List of symbols with 'symbol' and 'exchange' keys",
        examples=[[{"symbol": "AAPL", "exchange": "NASDAQ"}]],
    )
    interval: Interval = Field(default=Interval.DAY_1, description="Time interval")
    n_bars: int = Field(
        default=LIMIT_TVDATAFEED_MAX_BARS,
        ge=1,
        le=LIMIT_TVDATAFEED_MAX_BARS,
        description="Number of bars to fetch",
    )
