"""Background jobs for market data synchronization."""

from src.common.jobs import JobScheduler
from src.common.logging import get_logger
from src.config import get_settings
from src.features.market_data.models.ohlcv import Interval
from src.features.market_data.repositories.ohlcv_repository import OHLCVRepository
from src.features.market_data.services.data_sync_service import DataSyncService

logger = get_logger(__name__)


async def sync_all_symbols() -> None:
    """Sync all tracked symbols with their configured intervals.

    This job runs periodically to keep data up-to-date.
    """
    logger.info("sync_all_symbols_start")

    settings = get_settings()
    service = DataSyncService(settings)

    try:
        # Get all symbols that have been synced before
        statuses = await OHLCVRepository.get_all_sync_statuses()

        if not statuses:
            logger.info("sync_all_symbols_no_symbols")
            return

        synced_count = 0
        error_count = 0

        for status in statuses:
            try:
                interval = Interval(status.interval)
                result = await service.sync_symbol(
                    symbol=status.symbol,
                    exchange=status.exchange,
                    interval=interval,
                    n_bars=500,  # Only fetch recent bars for updates
                )

                if result["status"] == "completed":
                    synced_count += 1
                else:
                    error_count += 1

            except Exception as e:
                logger.error(
                    "sync_symbol_job_error",
                    symbol=status.symbol,
                    exchange=status.exchange,
                    error=str(e),
                )
                error_count += 1

        logger.info(
            "sync_all_symbols_complete",
            synced=synced_count,
            errors=error_count,
            total=len(statuses),
        )

    finally:
        service.close()


async def sync_daily_data() -> None:
    """Sync daily data for all tracked symbols.

    This is a lighter job that runs more frequently.
    """
    logger.info("sync_daily_data_start")

    settings = get_settings()
    service = DataSyncService(settings)

    try:
        statuses = await OHLCVRepository.get_all_sync_statuses()

        # Only sync daily interval
        daily_statuses = [s for s in statuses if s.interval == Interval.DAY_1.value]

        for status in daily_statuses:
            await service.sync_symbol(
                symbol=status.symbol,
                exchange=status.exchange,
                interval=Interval.DAY_1,
                n_bars=10,  # Just get the latest bars
            )

        logger.info("sync_daily_data_complete", count=len(daily_statuses))

    finally:
        service.close()


def register_sync_jobs() -> None:
    """Register market data sync jobs with the scheduler."""

    # Sync all symbols every 6 hours
    JobScheduler.add_interval_job(
        sync_all_symbols,
        job_id="market_data_sync_all",
        hours=6,
    )

    # Sync daily data every hour during market hours (Mon-Fri, 9-17 UTC)
    JobScheduler.add_cron_job(
        sync_daily_data,
        job_id="market_data_sync_daily",
        hour="9-17",
        minute="0",
        day_of_week="mon-fri",
    )

    logger.info("market_data_sync_jobs_registered")
