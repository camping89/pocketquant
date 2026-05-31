"""Response DTO builders for sync_one. Pure functions — no I/O."""

from pocketquant.api.market_data.handlers.sync.dto import SyncResponse
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval


def build_success(
    symbol: str,
    interval: Interval,
    *,
    bars_synced: int,
    bars_fetched: int,
    filtered_existing: int,
    filtered_misaligned: int,
    total_bars: int,
    latest_bar: Bar | None,
) -> SyncResponse:
    """Build a completed SyncResponse. ``symbol`` is composite ``{code}:{exchange}``."""
    return SyncResponse(
        symbol=symbol,
        interval=interval.value,
        status="completed",
        bars_synced=bars_synced,
        bars_fetched=bars_fetched,
        filtered_existing=filtered_existing,
        filtered_misaligned=filtered_misaligned,
        total_bars=total_bars,
        last_bar_at=(
            latest_bar.datetime.isoformat() if latest_bar and latest_bar.datetime else None
        ),
    )
