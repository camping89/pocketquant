"""Background sync jobs for market data — tiered by timeframe cadence."""

from pocketquant.api.market_data.handlers.sync import SyncSymbolCommand
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infrastructure.scheduling.scheduler import JobScheduler
from pocketquant.core.persistence.repositories.sync_status_repository import SyncStatusRepository

logger = get_logger(__name__)

# Canonical timeframes synced across all tracked symbols
SYNC_INTERVALS = [
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
]


async def _sync_by_intervals(
    intervals: list[Interval],
    n_bars: int,
    job_name: str,
    mediator: Mediator,
    sync_status_repo: SyncStatusRepository,
) -> None:
    """Generic sync: for each tracked symbol, sync the given intervals."""
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


def register_sync_jobs(
    mediator: Mediator,
    job_scheduler: JobScheduler,
    sync_status_repo: SyncStatusRepository,
) -> None:
    """Register 6 tiered background sync jobs with the scheduler."""
    async def sync_5m():
        await _sync_by_intervals([Interval.MINUTE_5], 30, "sync_5m", mediator, sync_status_repo)

    async def sync_15m():
        await _sync_by_intervals([Interval.MINUTE_15], 30, "sync_15m", mediator, sync_status_repo)

    async def sync_hourly():
        await _sync_by_intervals([Interval.HOUR_1], 10, "sync_hourly", mediator, sync_status_repo)

    async def sync_swing():
        await _sync_by_intervals([Interval.HOUR_4], 6, "sync_swing", mediator, sync_status_repo)

    async def sync_daily():
        await _sync_by_intervals([Interval.DAY_1], 7, "sync_daily", mediator, sync_status_repo)

    async def sync_backfill():
        await _sync_by_intervals(SYNC_INTERVALS, 5000, "sync_backfill", mediator, sync_status_repo)

    job_scheduler.add_interval_job(sync_5m, job_id="sync_5m", minutes=5)
    job_scheduler.add_interval_job(sync_15m, job_id="sync_15m", minutes=15)
    job_scheduler.add_interval_job(sync_hourly, job_id="sync_hourly", hours=1)
    job_scheduler.add_interval_job(sync_swing, job_id="sync_swing", hours=4)
    job_scheduler.add_cron_job(sync_daily, job_id="sync_daily", hour=0, minute=30)
    job_scheduler.add_cron_job(sync_backfill, job_id="sync_backfill", hour=3, minute=0)

    logger.info("market_data.registered_sync_jobs", job_count=6)
