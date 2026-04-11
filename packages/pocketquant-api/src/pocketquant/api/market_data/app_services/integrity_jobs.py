"""Integrity check and repair functions for bar data."""

from datetime import UTC, datetime, timedelta

from pocketquant.api.market_data.handlers.sync import SyncSymbolCommand
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.domain.bar.services.bar_builder import get_bar_start, is_bar_aligned
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.shared.value_objects import INTERVAL_SECONDS
from pocketquant.core.persistence.repositories.bar_repository import BarRepository

logger = get_logger(__name__)


def _group_gaps(
    missing: list[datetime], step: timedelta
) -> list[tuple[datetime, datetime]]:
    """Group consecutive missing timestamps into (start, end) ranges."""
    if not missing:
        return []
    ranges: list[tuple[datetime, datetime]] = []
    start = missing[0]
    prev = missing[0]
    for ts in missing[1:]:
        if ts - prev > step:
            ranges.append((start, prev))
            start = ts
        prev = ts
    ranges.append((start, prev))
    return ranges


async def check_integrity(
    symbol: str,
    exchange: str,
    interval: Interval,
    bar_repo: BarRepository,
    days_back: int = 7,
) -> dict:
    """Check bar alignment + gaps. Returns misaligned docs, missing count, gap ranges.

    Note: Only reliable for 24/7 markets (crypto). Equity symbols with market hours
    will produce false-positive gap detections on weekends/holidays.
    """
    # Use naive datetimes — MongoDB returns naive, so set arithmetic must match
    end = datetime.now(UTC).replace(tzinfo=None)
    start = end - timedelta(days=days_back)
    docs = await bar_repo.find_datetimes(symbol, exchange, interval, start, end)

    misaligned = [d for d in docs if not is_bar_aligned(d["datetime"], interval)]
    aligned_times = {d["datetime"] for d in docs if is_bar_aligned(d["datetime"], interval)}

    seconds = INTERVAL_SECONDS[interval]
    grid_start = get_bar_start(start, interval)
    expected: set[datetime] = set()
    t = grid_start
    while t <= end:
        expected.add(t)
        t += timedelta(seconds=seconds)

    missing = sorted(expected - aligned_times)
    gap_ranges = _group_gaps(missing, timedelta(seconds=seconds))

    return {
        "symbol": symbol.upper(),
        "exchange": exchange.upper(),
        "interval": interval.value,
        "total": len(docs),
        "misaligned_count": len(misaligned),
        "misaligned_ids": [str(d["_id"]) for d in misaligned],
        "missing_count": len(missing),
        "gap_ranges": [(s.isoformat(), e.isoformat()) for s, e in gap_ranges],
    }


async def repair_integrity(
    symbol: str,
    exchange: str,
    interval: Interval,
    bar_repo: BarRepository,
    mediator: Mediator,
    days_back: int = 7,
) -> dict:
    """Delete misaligned bars + resync gaps via existing sync pipeline."""
    report = await check_integrity(symbol, exchange, interval, bar_repo, days_back)

    deleted = 0
    if report["misaligned_ids"]:
        deleted = await bar_repo.delete_many_by_ids(report["misaligned_ids"])

    resynced = 0
    if report["gap_ranges"]:
        try:
            command = SyncSymbolCommand(
                symbol=symbol, exchange=exchange, interval=interval, n_bars=5000,
            )
            await mediator.send(command)
            resynced = len(report["gap_ranges"])
        except Exception as e:
            logger.error(
                "integrity.resync_failed",
                symbol=symbol, interval=interval.value, error=str(e),
            )

    return {
        "symbol": symbol.upper(),
        "exchange": exchange.upper(),
        "interval": interval.value,
        "deleted": deleted,
        "gaps_resynced": resynced,
        "missing_before": report["missing_count"],
    }
