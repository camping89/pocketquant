"""Background sync jobs for market data — tiered by timeframe cadence.

All job entrypoints (sync_5m, sync_15m, ...) are module-level coroutines so
APScheduler can serialize them as text references for MongoDBJobStore.
Dependencies (mediator, repos) are resolved at job-execution time from a
module-level container reference set by `register_sync_jobs`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pocketquant.api.market_data.app_services.integrity_jobs import (
    check_integrity,
    repair_integrity,
)
from pocketquant.api.market_data.handlers.sync import SyncSymbolCommand
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infrastructure.scheduling.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.core.infrastructure.scheduling.scheduler import JobScheduler
from pocketquant.core.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)

if TYPE_CHECKING:
    from dishka import AsyncContainer

logger = get_logger(__name__)

# Canonical timeframes synced across all tracked symbols
SYNC_INTERVALS = [
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
]

# ---------------------------------------------------------------------------
# Module-level container reference. Set once at startup by register_sync_jobs.
# Job functions resolve their dependencies via this container at execution time.
# ---------------------------------------------------------------------------

_container: AsyncContainer | None = None


def set_container(container: AsyncContainer) -> None:
    global _container
    _container = container


def _get_container() -> AsyncContainer:
    if _container is None:
        raise RuntimeError(
            "sync_jobs container not initialized. "
            "Call set_container() before scheduler executes any job."
        )
    return _container


def _ms_since(started: datetime) -> int:
    return int((datetime.now(UTC) - started).total_seconds() * 1000)


# ---------------------------------------------------------------------------
# Internal sync engine — shared by all interval-based jobs
# ---------------------------------------------------------------------------


async def _sync_by_intervals(
    intervals: list[Interval],
    n_bars: int,
    job_name: str,
    mediator: Mediator,
    sync_status_repo: SyncStatusRepository,
) -> None:
    """For each tracked symbol, sync the given intervals."""
    logger.info(f"market_data.{job_name}.started")

    statuses = await sync_status_repo.find_all()
    symbols = list({(s.symbol, s.exchange) for s in statuses})

    if not symbols:
        logger.info(f"market_data.{job_name}.skipped", reason="no_tracked_symbols")
        return

    synced = 0
    errors = 0
    first_error: Exception | None = None

    for symbol, exchange in symbols:
        for interval in intervals:
            try:
                command = SyncSymbolCommand(
                    symbol=symbol, exchange=exchange, interval=interval, n_bars=n_bars,
                )
                result = await mediator.send(command)
                if result.status == "completed":
                    synced += 1
                else:
                    errors += 1
            except Exception as e:
                logger.error(
                    f"market_data.{job_name}.symbol_failed",
                    symbol=symbol,
                    exchange=exchange,
                    interval=interval.value,
                    error=str(e),
                )
                errors += 1
                first_error = first_error or e

    logger.info(f"market_data.{job_name}.completed", synced_count=synced, error_count=errors)
    if first_error:
        raise first_error


# ---------------------------------------------------------------------------
# Job runners — wrap actual work with history recording.
# History lives here (not in JobScheduler) because picklable text-ref jobs
# cannot be wrapped with closures.
# ---------------------------------------------------------------------------


async def _run_sync(name: str, intervals: list[Interval], n_bars: int) -> None:
    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    mediator = await container.get(Mediator)
    sync_status_repo = await container.get(SyncStatusRepository)

    started = datetime.now(UTC)
    doc_id: str | None = None
    try:
        doc_id = await history_repo.record_start(name)
    except Exception:
        logger.warning("job_history.record_start_failed", job_id=name, exc_info=True)

    try:
        await _sync_by_intervals(intervals, n_bars, name, mediator, sync_status_repo)
        if doc_id:
            await history_repo.record_finish(
                doc_id, status="completed", duration_ms=_ms_since(started)
            )
    except Exception as exc:
        if doc_id:
            try:
                await history_repo.record_finish(
                    doc_id,
                    status="failed",
                    duration_ms=_ms_since(started),
                    error=str(exc),
                )
            except Exception:
                logger.warning(
                    "job_history.record_finish_failed", job_id=name, exc_info=True
                )
        raise


async def _run_integrity(name: str) -> None:
    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    sync_status_repo = await container.get(SyncStatusRepository)
    bar_repo = await container.get(BarRepository)

    started = datetime.now(UTC)
    doc_id: str | None = None
    try:
        doc_id = await history_repo.record_start(name)
    except Exception:
        logger.warning("job_history.record_start_failed", job_id=name, exc_info=True)

    try:
        statuses = await sync_status_repo.find_all()
        symbols = list({(s.symbol, s.exchange) for s in statuses})
        for symbol, exchange in symbols:
            for interval in SYNC_INTERVALS:
                report = await check_integrity(symbol, exchange, interval, bar_repo)
                if report["misaligned_count"] or report["missing_count"]:
                    logger.warning(
                        "integrity.issues_found",
                        symbol=symbol, exchange=exchange, interval=interval.value,
                        misaligned=report["misaligned_count"],
                        missing=report["missing_count"],
                    )
        if doc_id:
            await history_repo.record_finish(
                doc_id, status="completed", duration_ms=_ms_since(started)
            )
    except Exception as exc:
        if doc_id:
            try:
                await history_repo.record_finish(
                    doc_id,
                    status="failed",
                    duration_ms=_ms_since(started),
                    error=str(exc),
                )
            except Exception:
                logger.warning(
                    "job_history.record_finish_failed", job_id=name, exc_info=True
                )
        raise


async def _run_repair(name: str) -> None:
    container = _get_container()
    history_repo = await container.get(JobHistoryRepository)
    mediator = await container.get(Mediator)
    sync_status_repo = await container.get(SyncStatusRepository)
    bar_repo = await container.get(BarRepository)

    started = datetime.now(UTC)
    doc_id: str | None = None
    try:
        doc_id = await history_repo.record_start(name)
    except Exception:
        logger.warning("job_history.record_start_failed", job_id=name, exc_info=True)

    try:
        statuses = await sync_status_repo.find_all()
        symbols = list({(s.symbol, s.exchange) for s in statuses})
        for symbol, exchange in symbols:
            for interval in SYNC_INTERVALS:
                result = await repair_integrity(
                    symbol, exchange, interval, bar_repo, mediator
                )
                if result["deleted"] or result["gaps_resynced"]:
                    logger.info(
                        "integrity.repaired",
                        symbol=symbol, exchange=exchange, interval=interval.value,
                        deleted=result["deleted"],
                        gaps_resynced=result["gaps_resynced"],
                    )
        if doc_id:
            await history_repo.record_finish(
                doc_id, status="completed", duration_ms=_ms_since(started)
            )
    except Exception as exc:
        if doc_id:
            try:
                await history_repo.record_finish(
                    doc_id,
                    status="failed",
                    duration_ms=_ms_since(started),
                    error=str(exc),
                )
            except Exception:
                logger.warning(
                    "job_history.record_finish_failed", job_id=name, exc_info=True
                )
        raise


# ---------------------------------------------------------------------------
# Picklable job entrypoints — referenced by APScheduler as
# "pocketquant.api.market_data.app_services.sync_jobs:<funcname>"
# ---------------------------------------------------------------------------


async def sync_5m() -> None:
    await _run_sync("sync_5m", [Interval.MINUTE_5], 30)


async def sync_15m() -> None:
    await _run_sync("sync_15m", [Interval.MINUTE_15], 30)


async def sync_hourly() -> None:
    await _run_sync("sync_hourly", [Interval.HOUR_1], 10)


async def sync_swing() -> None:
    await _run_sync("sync_swing", [Interval.HOUR_4], 6)


async def sync_daily() -> None:
    await _run_sync("sync_daily", [Interval.DAY_1], 7)


async def sync_backfill() -> None:
    await _run_sync("sync_backfill", SYNC_INTERVALS, 5000)


async def sync_integrity() -> None:
    await _run_integrity("sync_integrity")


async def sync_repair() -> None:
    await _run_repair("sync_repair")


# ---------------------------------------------------------------------------
# Registration entrypoint
# ---------------------------------------------------------------------------


_MODULE = "pocketquant.api.market_data.app_services.sync_jobs"


def register_sync_jobs(
    container: AsyncContainer,
    job_scheduler: JobScheduler,
) -> None:
    """Wire container reference + register 8 sync/integrity jobs as text refs."""
    set_container(container)

    job_scheduler.add_interval_job(f"{_MODULE}:sync_5m", job_id="sync_5m", minutes=5)
    job_scheduler.add_interval_job(f"{_MODULE}:sync_15m", job_id="sync_15m", minutes=15)
    job_scheduler.add_interval_job(f"{_MODULE}:sync_hourly", job_id="sync_hourly", hours=1)
    job_scheduler.add_interval_job(f"{_MODULE}:sync_swing", job_id="sync_swing", hours=4)
    job_scheduler.add_cron_job(
        f"{_MODULE}:sync_daily", job_id="sync_daily", hour=0, minute=30,
    )
    job_scheduler.add_cron_job(
        f"{_MODULE}:sync_backfill", job_id="sync_backfill", hour=3, minute=0,
    )
    job_scheduler.add_cron_job(
        f"{_MODULE}:sync_integrity", job_id="sync_integrity", hour=4, minute=0,
    )
    job_scheduler.add_interval_job(
        f"{_MODULE}:sync_repair", job_id="sync_repair", hours=12,
    )

    logger.info("market_data.registered_sync_jobs", job_count=8)
