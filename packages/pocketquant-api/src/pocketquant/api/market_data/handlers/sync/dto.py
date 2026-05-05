"""DTOs for sync operations."""

from pydantic import BaseModel


class SyncResponse(BaseModel):
    """Result of sync operation - used as handler return and API response."""

    symbol: str
    exchange: str
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
