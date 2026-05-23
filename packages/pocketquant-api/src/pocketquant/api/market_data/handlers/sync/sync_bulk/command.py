"""Bulk sync command for market data operations."""

from pocketquant.core.common.constants import LIMIT_TVDATAFEED_MAX_BARS
from pocketquant.core.domain.shared.value_objects import Interval
from pydantic import BaseModel, Field


class BulkSyncCommand(BaseModel):
    """Sync multiple composite symbols in sequence.

    Each entry in ``symbols`` must be a composite ``{code}:{exchange}`` string
    (e.g. ``"BTCUSDT:BINANCE"``).
    """

    symbols: list[str] = Field(
        ...,
        description="List of composite symbol strings, e.g. ['BTCUSDT:BINANCE']",
        examples=[["BTCUSDT:BINANCE", "ETHUSDT:BINANCE"]],
    )
    interval: Interval = Field(default=Interval.DAY_1, description="Time interval")
    n_bars: int = Field(
        default=LIMIT_TVDATAFEED_MAX_BARS,
        ge=1,
        le=LIMIT_TVDATAFEED_MAX_BARS,
        description="Number of bars to fetch",
    )
