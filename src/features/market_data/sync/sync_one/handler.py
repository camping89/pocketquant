"""Handler for sync symbol command."""

from datetime import UTC, datetime

from src.common.cache import Cache
from src.common.constants import build_ohlcv_cache_key
from src.common.logging import get_logger
from src.common.mediator import Handler, handles
from src.common.messaging import EventBus
from src.domain.ohlcv import OHLCVAggregate
from src.domain.ohlcv.entities import Bar
from src.domain.shared.value_objects import Interval as DomainInterval
from src.domain.symbol import SymbolAggregate
from src.features.market_data.sync.dto import SyncResponse
from src.features.market_data.sync.sync_one.command import SyncSymbolCommand
from src.infrastructure.tradingview import TradingViewClient
from src.persistence.repositories.ohlcv_repository import OHLCVRepository
from src.persistence.repositories.symbol_repository import SymbolRepository
from src.persistence.repositories.sync_status_repository import SyncStatusRepository

logger = get_logger(__name__)


@handles(SyncSymbolCommand)
class SyncSymbolHandler(Handler[SyncSymbolCommand, SyncResponse]):
    """Handle syncing a single symbol."""

    def __init__(
        self,
        provider: TradingViewClient,
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
        interval = request.interval

        logger.info(
            "market_data.sync.started",
            symbol=symbol,
            exchange=exchange,
            interval=interval.value,
        )

        await self._sync_status_repo.upsert(symbol, exchange, interval, "syncing")

        try:
            records = await self._fetch_bars(symbol, exchange, interval, request.n_bars)
            if not records:
                return await self._fail(
                    symbol, exchange, interval, "No data returned from provider"
                )

            upserted_count = await self._persist_bars(symbol, exchange, records)
            total_bars, latest_bar = await self._get_bar_stats(
                symbol, exchange, interval
            )

            await self._mark_completed(
                symbol, exchange, interval, total_bars, latest_bar
            )
            await self._invalidate_cache(symbol, exchange, interval)
            await self._publish_sync_event(
                symbol, exchange, interval, upserted_count, latest_bar
            )

            logger.info(
                "market_data.sync.completed",
                symbol=symbol,
                exchange=exchange,
                bars_synced=upserted_count,
            )
            return self._success(
                symbol, exchange, interval, upserted_count, total_bars, latest_bar
            )

        except Exception as e:
            logger.error(
                "market_data.sync.failed",
                symbol=symbol,
                exchange=exchange,
                interval=interval.value,
                error=str(e),
            )
            return await self._fail(symbol, exchange, interval, str(e))

    # -- Private helpers (each does one thing) --

    async def _fetch_bars(
        self,
        symbol: str,
        exchange: str,
        interval: DomainInterval,
        n_bars: int,
    ) -> list[Bar]:
        return await self.provider.fetch_ohlcv(
            symbol=symbol, exchange=exchange, interval=interval, n_bars=n_bars
        )

    async def _persist_bars(
        self, symbol: str, exchange: str, records: list[Bar]
    ) -> int:
        upserted_count = await self._ohlcv_repo.upsert_many(records)
        await self._symbol_repo.upsert(SymbolAggregate.create(code=symbol, exchange=exchange))
        return upserted_count

    async def _get_bar_stats(
        self, symbol: str, exchange: str, interval: DomainInterval
    ) -> tuple[int, Bar | None]:
        total_bars = await self._ohlcv_repo.count(symbol, exchange, interval)
        latest_bar = await self._ohlcv_repo.get_latest(symbol, exchange, interval)
        return total_bars, latest_bar

    async def _mark_completed(
        self,
        symbol: str,
        exchange: str,
        interval: DomainInterval,
        bar_count: int,
        latest_bar: Bar | None,
    ) -> None:
        await self._sync_status_repo.upsert(
            symbol,
            exchange,
            interval,
            "completed",
            bar_count=bar_count,
            last_bar_at=latest_bar.datetime if latest_bar else None,
        )

    async def _invalidate_cache(
        self, symbol: str, exchange: str, interval: DomainInterval
    ) -> None:
        cache_key = build_ohlcv_cache_key(symbol, exchange, interval.value)
        await self._cache.delete_pattern(f"{cache_key}:*")

    async def _publish_sync_event(
        self,
        symbol: str,
        exchange: str,
        interval: DomainInterval,
        bars_count: int,
        latest_bar: Bar | None,
    ) -> None:
        aggregate = OHLCVAggregate(symbol=symbol, exchange=exchange)
        aggregate.record_sync(
            interval=DomainInterval(interval.value),
            bars_count=bars_count,
            last_bar_at=latest_bar.datetime if latest_bar else datetime.now(UTC),
        )
        await self.event_bus.publish_all(aggregate.get_uncommitted_events())

    def _success(
        self,
        symbol: str,
        exchange: str,
        interval: DomainInterval,
        bars_synced: int,
        total_bars: int,
        latest_bar: Bar | None,
    ) -> SyncResponse:
        return SyncResponse(
            symbol=symbol,
            exchange=exchange,
            interval=interval.value,
            status="completed",
            bars_synced=bars_synced,
            total_bars=total_bars,
            last_bar_at=latest_bar.datetime.isoformat() if latest_bar else None,
        )

    async def _fail(
        self, symbol: str, exchange: str, interval: DomainInterval, message: str
    ) -> SyncResponse:
        await self._sync_status_repo.upsert(
            symbol, exchange, interval, "error", error_message=message
        )
        return SyncResponse(
            symbol=symbol,
            exchange=exchange,
            interval=interval.value,
            status="error",
            message=message,
            bars_synced=0,
        )
