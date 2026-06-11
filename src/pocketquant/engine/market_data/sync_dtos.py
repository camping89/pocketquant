"""Sync operation DTOs — shared between SyncService and sync_internals helpers.

Kept in a standalone module to avoid circular imports between sync_service and
sync_internals/responses (which builds SyncResponse instances).
"""

from pydantic import BaseModel, Field

from pocketquant.core.common.constants import LIMIT_TVDATAFEED_MAX_BARS
from pocketquant.core.domain.shared.enums import Interval as DomainInterval


class SyncSymbolCommand(BaseModel):
    """Sync historical OHLCV data for a single composite symbol.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    symbol: str = Field(..., description="Composite symbol (e.g., BTCUSDT:BINANCE)")
    interval: DomainInterval = Field(default=DomainInterval.DAY_1, description="Time interval")
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
    interval: DomainInterval = Field(default=DomainInterval.DAY_1, description="Time interval")
    n_bars: int = Field(
        default=LIMIT_TVDATAFEED_MAX_BARS,
        ge=1,
        le=LIMIT_TVDATAFEED_MAX_BARS,
        description="Number of bars to fetch",
    )


class SyncResponse(BaseModel):
    """Result of sync operation. ``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
    interval: str
    status: str
    bars_synced: int = 0
    # Raw fetch count from provider (before filters).
    bars_fetched: int = 0
    # Bars dropped because they already exist in DB.
    filtered_existing: int = 0
    # Bars dropped because timestamps don't align to the interval grid.
    filtered_misaligned: int = 0
    total_bars: int | None = None
    last_bar_at: str | None = None
    message: str | None = None
