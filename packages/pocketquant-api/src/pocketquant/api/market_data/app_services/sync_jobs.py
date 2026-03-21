"""Background sync jobs for market data — receives dependencies via params."""

from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.domain.shared.value_objects import Interval
from pocketquant.api.market_data.handlers.sync import SyncSymbolCommand
from pocketquant.core.infrastructure.scheduling.scheduler import JobScheduler
from pocketquant.core.persistence.repositories.sync_status_repository import SyncStatusRepository

logger = get_logger(__name__)


async def _sync_all_symbols(mediator: Mediator, sync_status_repo: SyncStatusRepository) -> None:
    logger.info("market_data.sync_all.started")

    statuses = await sync_status_repo.find_all()

    if not statuses:
        logger.info("market_data.sync_all.skipped", reason="no_tracked_symbols")
        return

    synced_count = 0
    error_count = 0
    errors: list[Exception] = []

    for status in statuses:
        try:
            cmd = SyncSymbolCommand(
                symbol=status.symbol,
                exchange=status.exchange,
                interval=Interval(status.interval),
                n_bars=500,
            )
            result = await mediator.send(cmd)

            if result.status == "completed":
                synced_count += 1
            else:
                error_count += 1

        except Exception as e:
            logger.error(
                "market_data.sync_all.symbol_failed",
                symbol=status.symbol,
                exchange=status.exchange,
                error=str(e),
            )
            error_count += 1
            errors.append(e)

    logger.info(
        "market_data.sync_all.completed",
        synced_count=synced_count,
        error_count=error_count,
        total_symbols=len(statuses),
    )

    if errors:
        raise errors[0]


async def _sync_daily_data(mediator: Mediator, sync_status_repo: SyncStatusRepository) -> None:
    logger.info("market_data.sync_daily.started")

    statuses = await sync_status_repo.find_all()
    daily_statuses = [s for s in statuses if s.interval == Interval.DAY_1.value]

    synced_count = 0
    error_count = 0
    errors: list[Exception] = []

    for status in daily_statuses:
        try:
            cmd = SyncSymbolCommand(
                symbol=status.symbol,
                exchange=status.exchange,
                interval=Interval.DAY_1,
                n_bars=10,
            )
            await mediator.send(cmd)
            synced_count += 1
        except Exception as e:
            logger.error(
                "market_data.sync_daily.symbol_failed",
                symbol=status.symbol,
                exchange=status.exchange,
                error=str(e),
            )
            error_count += 1
            errors.append(e)

    logger.info(
        "market_data.sync_daily.completed",
        synced_count=synced_count,
        error_count=error_count,
    )

    if errors:
        raise errors[0]


def register_sync_jobs(
    mediator: Mediator,
    job_scheduler: JobScheduler,
    sync_status_repo: SyncStatusRepository,
) -> None:
    """Register background sync jobs with the scheduler."""
    job_scheduler.add_interval_job(
        _sync_all_symbols,
        job_id="market_data_sync_all",
        hours=6,
        mediator=mediator,
        sync_status_repo=sync_status_repo,
    )

    job_scheduler.add_cron_job(
        _sync_daily_data,
        job_id="market_data_sync_daily",
        hour="9-17",
        minute="0",
        day_of_week="mon-fri",
        mediator=mediator,
        sync_status_repo=sync_status_repo,
    )

    logger.info("market_data.registered_sync_jobs")
