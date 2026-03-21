"""DTOs for sync operations."""

from pydantic import BaseModel


class SyncResponse(BaseModel):
    """Result of sync operation - used as handler return and API response."""

    symbol: str
    exchange: str
    interval: str
    status: str
    bars_synced: int = 0
    total_bars: int | None = None
    last_bar_at: str | None = None
    message: str | None = None
