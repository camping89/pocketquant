"""DTOs for status operations."""

from dataclasses import dataclass


@dataclass
class SyncStatusResult:
    """Result of a sync status query."""

    symbol: str
    exchange: str
    interval: str
    status: str
    bar_count: int | None = None
    last_sync_at: str | None = None
    last_bar_at: str | None = None
    error_message: str | None = None


@dataclass
class StatusResult:
    """Result of a service status query."""

    running: bool
    subscription_count: int
    active_symbols: list[str]
