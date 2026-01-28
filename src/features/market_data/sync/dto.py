"""DTOs for sync operations."""

from dataclasses import dataclass


@dataclass
class SyncResult:
    """Result of a sync operation."""

    symbol: str
    exchange: str
    interval: str
    status: str
    bars_synced: int = 0
    total_bars: int | None = None
    last_bar_at: str | None = None
    message: str | None = None
