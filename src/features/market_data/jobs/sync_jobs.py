from src.common.jobs import JobScheduler
from src.common.logging import get_logger
from src.config import get_settings
from src.features.market_data.models.ohlcv import Interval
from src.features.market_data.repositories.ohlcv_repository import OHLCVRepository
from src.features.market_data.services.data_sync_service import DataSyncService

logger = get_logger(__name__)


async def sync_all_symbols() -> None:
    logger.info("sync_all_symbols_start")

    settings = get_settings()
    service = DataSyncService(settings)

    try:
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
                    n_bars=500,
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
    logger.info("sync_daily_data_start")

    settings = get_settings()
    service = DataSyncService(settings)

    try:
        statuses = await OHLCVRepository.get_all_sync_statuses()

        daily_statuses = [s for s in statuses if s.interval == Interval.DAY_1.value]

        for status in daily_statuses:
            await service.sync_symbol(
                symbol=status.symbol,
                exchange=status.exchange,
                interval=Interval.DAY_1,
                n_bars=10,
            )

        logger.info("sync_daily_data_complete", count=len(daily_statuses))

    finally:
        service.close()


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

    logger.info("market_data_sync_jobs_registered")
