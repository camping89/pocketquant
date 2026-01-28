from src.common.constants import COLLECTION_SYNC_STATUS
from src.common.database import Database
from src.common.jobs import JobScheduler
from src.common.logging import get_logger
from src.common.mediator import Mediator
from src.features.market_data.models.ohlcv import Interval, SyncStatus
from src.features.market_data.sync import SyncSymbolCommand

logger = get_logger(__name__)

_mediator: Mediator | None = None


def set_mediator(mediator: Mediator) -> None:
    """Set the mediator instance for background jobs."""
    global _mediator
    _mediator = mediator


async def _get_all_sync_statuses() -> list[SyncStatus]:
    collection = Database.get_collection(COLLECTION_SYNC_STATUS)
    cursor = collection.find()
    return [SyncStatus.from_mongo(doc) async for doc in cursor]


async def sync_all_symbols() -> None:
    if not _mediator:
        logger.error("market_data.sync_all.skipped", reason="mediator_not_set")
        return

    logger.info("market_data.sync_all.started")

    statuses = await _get_all_sync_statuses()

    if not statuses:
        logger.info("market_data.sync_all.skipped", reason="no_tracked_symbols")
        return

    synced_count = 0
    error_count = 0

    for status in statuses:
        try:
            cmd = SyncSymbolCommand(
                symbol=status.symbol,
                exchange=status.exchange,
                interval=status.interval,
                n_bars=500,
            )
            result = await _mediator.send(cmd)

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

    logger.info(
        "market_data.sync_all.completed",
        synced_count=synced_count,
        error_count=error_count,
        total_symbols=len(statuses),
    )


async def sync_daily_data() -> None:
    if not _mediator:
        logger.error("market_data.sync_daily.skipped", reason="mediator_not_set")
        return

    logger.info("market_data.sync_daily.started")

    statuses = await _get_all_sync_statuses()
    daily_statuses = [s for s in statuses if s.interval == Interval.DAY_1.value]

    for status in daily_statuses:
        cmd = SyncSymbolCommand(
            symbol=status.symbol,
            exchange=status.exchange,
            interval=Interval.DAY_1.value,
            n_bars=10,
        )
        await _mediator.send(cmd)

    logger.info("market_data.sync_daily.completed", synced_count=len(daily_statuses))


def register_sync_jobs() -> None:
    JobScheduler.add_interval_job(
        sync_all_symbols,
        job_id="market_data_sync_all",
        hours=6,
    )

    JobScheduler.add_cron_job(
        sync_daily_data,
        job_id="market_data_sync_daily",
        hour="9-17",
        minute="0",
        day_of_week="mon-fri",
    )

    logger.info("market_data.registered_sync_jobs")
