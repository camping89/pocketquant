"""Handler for sync symbol command."""

from datetime import UTC, datetime

from src.common.cache import Cache
from src.common.constants import build_ohlcv_cache_key
from src.common.logging import get_logger
from src.common.mediator import Handler, handles
from src.common.messaging import EventBus
from src.domain.ohlcv import OHLCVAggregate
from src.domain.shared.value_objects import Interval as DomainInterval
from src.features.market_data.sync.dto import SyncResponse
from src.features.market_data.sync.sync_one.command import SyncSymbolCommand
from src.infrastructure.tradingview import TradingViewProvider
from src.persistence.repositories.ohlcv_repository import OHLCVRepository
from src.persistence.repositories.symbol_repository import SymbolRepository
from src.persistence.repositories.sync_status_repository import SyncStatusRepository
from src.persistence.schemas.symbol_schema import SymbolCreate

logger = get_logger(__name__)


@handles(SyncSymbolCommand)
class SyncSymbolHandler(Handler[SyncSymbolCommand, SyncResponse]):
    """Handle syncing a single symbol."""

    def __init__(
        self,
        provider: TradingViewProvider,
        event_bus: EventBus,
        cache: Cache,
        ohlcv_repository: OHLCVRepository,
        symbol_repository: SymbolRepository,
        sync_status_repository: SyncStatusRepository,
    ):
        self.provider = provider
        self.event_bus = event_bus
        self._cache = cache
        self._ohlcv_repo = ohlcv_repository
        self._symbol_repo = symbol_repository
        self._sync_status_repo = sync_status_repository

    async def handle(self, request: SyncSymbolCommand) -> SyncResponse:
        symbol = request.symbol.upper()
        exchange = request.exchange.upper()
        interval = request.interval  # Already Interval enum from Pydantic

        logger.info(
            "market_data.sync.started",
            symbol=symbol,
            exchange=exchange,
            interval=interval.value,
        )

        await self._sync_status_repo.upsert(symbol, exchange, interval, "syncing")

        try:
            records = await self.provider.fetch_ohlcv(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                n_bars=request.n_bars,
            )

            if not records:
                await self._sync_status_repo.upsert(
                    symbol,
                    exchange,
                    interval,
                    "error",
                    error_message="No data returned from provider",
                )
                return SyncResponse(
                    symbol=symbol,
                    exchange=exchange,
                    interval=interval.value,
                    status="error",
                    message="No data returned from provider",
                    bars_synced=0,
                )

            upserted_count = await self._ohlcv_repo.upsert_many(records)
            await self._symbol_repo.upsert(SymbolCreate(symbol=symbol, exchange=exchange))

            total_bars = await self._ohlcv_repo.count(symbol, exchange, interval)
            latest_bar = await self._ohlcv_repo.get_latest(symbol, exchange, interval)

            await self._sync_status_repo.upsert(
                symbol,
                exchange,
                interval,
                "completed",
                bar_count=total_bars,
                last_bar_at=latest_bar.datetime if latest_bar else None,
            )

            cache_key = build_ohlcv_cache_key(symbol, exchange, interval.value)
            await self._cache.delete_pattern(f"{cache_key}:*")

            aggregate = OHLCVAggregate(symbol=symbol, exchange=exchange)
            aggregate.record_sync(
                interval=DomainInterval(interval.value),
                bars_count=upserted_count,
                last_bar_at=latest_bar.datetime if latest_bar else datetime.now(UTC),
            )
            await self.event_bus.publish_all(aggregate.get_uncommitted_events())

            result = SyncResponse(
                symbol=symbol,
                exchange=exchange,
                interval=interval.value,
                status="completed",
                bars_synced=upserted_count,
                total_bars=total_bars,
                last_bar_at=latest_bar.datetime.isoformat() if latest_bar else None,
            )

            logger.info(
                "market_data.sync.completed",
                symbol=symbol,
                exchange=exchange,
                bars_synced=upserted_count,
            )
            return result

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "market_data.sync.failed",
                symbol=symbol,
                exchange=exchange,
                interval=interval.value,
                error=error_msg,
            )

            await self._sync_status_repo.upsert(
                symbol, exchange, interval, "error", error_message=error_msg
            )

            return SyncResponse(
                symbol=symbol,
                exchange=exchange,
                interval=interval.value,
                status="error",
                message=error_msg,
                bars_synced=0,
            )
