"""Integrity check and repair functions for bar data.

All functions accept composite ``symbol`` (``{code}:{exchange}``) — no separate exchange param.
"""

from datetime import UTC, datetime, timedelta

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.services.bar_builder_domain_service import (
    get_bar_start,
    is_bar_aligned,
)
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.shared.value_objects import INTERVAL_SECONDS
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.market_data.sync_service import SyncService, SyncSymbolCommand

logger = get_logger(__name__)


def _group_gaps(missing: list[datetime], step: timedelta) -> list[tuple[datetime, datetime]]:
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


def _expected_instants(
    interval: Interval,
    start: datetime,
    end: datetime,
    calendar: ITradingCalendarPort,
) -> set[datetime]:
    """The instants a bar should exist at, according to the symbol's calendar."""
    if interval == Interval.DAY_1:
        return {calendar.session_open(d) for d in calendar.sessions(start, end)}

    return {
        instant
        for instant in calendar.trading_minutes(start, end)
        if instant == calendar.bar_start(instant, interval)
    }


async def check_integrity(
    symbol: str,
    interval: Interval,
    bar_repo: BarRepository,
    calendar: ITradingCalendarPort,
    days_back: int = 7,
) -> dict:
    """Check bar alignment + gaps for composite ``symbol``.

    Returns misaligned docs, missing count, gap ranges.

    The expected grid comes from the symbol's own calendar, so a market that
    closes overnight, at weekends or for a holiday reports those hours as shut
    rather than as gaps. Weekly bars are skipped outright: there is no agreed
    weekly convention across venues to check them against yet.
    """
    # Grid ends at last CLOSED bar — current incomplete bar can't exist in DB yet
    now = datetime.now(UTC)
    end = get_bar_start(now, interval)
    start = end - timedelta(days=days_back)
    docs = await bar_repo.find_datetimes(symbol, interval, start, end)

    misaligned, aligned_times = [], set()
    for d in docs:
        if is_bar_aligned(d["datetime"], interval, calendar):
            aligned_times.add(d["datetime"])
        else:
            misaligned.append(d)

    base = {
        "symbol": symbol.upper(),
        "interval": interval.value,
        "total": len(docs),
        "misaligned_count": len(misaligned),
        "misaligned_ids": [str(d["_id"]) for d in misaligned],
    }

    if interval == Interval.WEEK_1:
        # Deferred, not forgotten: repairing a weekly bar means deciding when a
        # week opens on each venue, and nothing downstream needs that answer yet.
        return {
            **base,
            "missing_count": 0,
            "gap_ranges": [],
            "skipped_reason": "weekly_convention",
        }

    step = timedelta(seconds=INTERVAL_SECONDS[interval])
    missing = sorted(_expected_instants(interval, start, end, calendar) - aligned_times)
    gap_ranges = _group_gaps(missing, step)

    return {
        **base,
        "missing_count": len(missing),
        "gap_ranges": [(s.isoformat(), e.isoformat()) for s, e in gap_ranges],
    }


async def repair_integrity(
    symbol: str,
    interval: Interval,
    bar_repo: BarRepository,
    sync_service: SyncService,
    calendar: ITradingCalendarPort,
    *,
    source: str,
    days_back: int = 7,
) -> dict:
    """Delete misaligned bars + resync gaps via sync pipeline (skip_filter=True).

    ``symbol`` is composite ``{code}:{exchange}``.
    """
    report = await check_integrity(symbol, interval, bar_repo, calendar, days_back)

    deleted = 0
    if report["misaligned_ids"]:
        deleted = await bar_repo.delete_many_by_ids(report["misaligned_ids"])

    resynced = 0
    if report.get("skipped_reason"):
        # Nothing to resync against: the check declined to compute a grid, so a
        # resync here would be guessing at which bars are missing.
        return {
            "symbol": symbol.upper(),
            "interval": interval.value,
            "deleted": deleted,
            "gaps_resynced": 0,
            "missing_before": 0,
            "still_missing": 0,
            "still_missing_ranges": [],
            "skipped_reason": report["skipped_reason"],
        }

    if report["gap_ranges"]:
        try:
            command = SyncSymbolCommand(
                symbol=symbol,
                interval=interval,
                n_bars=5000,
                skip_filter=True,
                source=source,
            )
            await sync_service.sync_one(command)
            resynced = len(report["gap_ranges"])
        except Exception as e:
            logger.error(
                "integrity.resync_failed",
                symbol=symbol,
                interval=interval.value,
                error=str(e),
            )

    # Verify: re-check integrity after repair
    verify = await check_integrity(symbol, interval, bar_repo, calendar, days_back)
    still_missing = verify["missing_count"]
    still_missing_ranges = verify["gap_ranges"]

    if still_missing > 0:
        logger.warning(
            "integrity.repair.still_missing",
            symbol=symbol,
            interval=interval.value,
            still_missing=still_missing,
            ranges=still_missing_ranges,
        )

    return {
        "symbol": symbol.upper(),
        "interval": interval.value,
        "deleted": deleted,
        "gaps_resynced": resynced,
        "missing_before": report["missing_count"],
        "still_missing": still_missing,
        "still_missing_ranges": still_missing_ranges,
    }
