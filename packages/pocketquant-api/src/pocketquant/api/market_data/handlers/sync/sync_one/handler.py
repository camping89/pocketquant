"""Handler for sync symbol command."""

from pocketquant.api.market_data.handlers.sync.dto import SyncResponse
from pocketquant.api.market_data.handlers.sync.sync_one.anomaly_log import emit_no_progress
from pocketquant.api.market_data.handlers.sync.sync_one.bar_filters import (
    drop_misaligned_bars,
    filter_new_bars,
)
from pocketquant.api.market_data.handlers.sync.sync_one.command import SyncSymbolCommand
from pocketquant.api.market_data.handlers.sync.sync_one.provider_fetch import fetch_with_retry
from pocketquant.api.market_data.handlers.sync.sync_one.responses import build_success
from pocketquant.core.common.cache import Cache
from pocketquant.core.common.constants import build_bar_cache_key
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.value_objects import Interval as DomainInterval
from pocketquant.core.domain.symbol import Symbol
from pocketquant.core.infrastructure.data_provider import IDataProvider
from pocketquant.core.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.persistence.repositories.sync_status_repository import SyncStatusRepository

logger = get_logger(__name__)


@handles(SyncSymbolCommand)
class SyncSymbolHandler(Handler[SyncSymbolCommand, SyncResponse]):
    """Handle syncing a single symbol."""

    def __init__(
        self,
        provider: IDataProvider,
        cache: Cache,
        bar_repository: BarRepository,
        symbol_repository: SymbolRepository,
        sync_status_repository: SyncStatusRepository,
    ):
        self.provider = provider
        self._cache = cache
        self._bar_repo = bar_repository
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
            bars_fetched = len(records)
            filtered_existing = 0
            filtered_misaligned = 0

            if records:
                # Skip existence filter on repair runs to allow gap filling.
                if not request.skip_filter:
                    pre = len(records)
                    records = await filter_new_bars(
                        records, symbol, exchange, interval, self._bar_repo,
                    )
                    filtered_existing = pre - len(records)
                pre_align = len(records)
                records = drop_misaligned_bars(records, interval)
                filtered_misaligned = pre_align - len(records)

            inserted_count = await self._persist_bars(symbol, exchange, records)
            total_bars, latest_bar = await self._get_bar_stats(symbol, exchange, interval)

            # Genuine first-sync failure: provider returned nothing AND no prior bars.
            if bars_fetched == 0 and total_bars == 0:
                return await self._fail(
                    symbol, exchange, interval, "No data returned from provider",
                )

            await self._mark_completed(symbol, exchange, interval, total_bars, latest_bar)
            await self._invalidate_cache(symbol, exchange, interval)

            # Single bump/reset decision: covers empty-fetch, all-misaligned,
            # and all-already-existing cases uniformly.
            if inserted_count > 0:
                await self._sync_status_repo.reset_empty_fetch(symbol, exchange, interval)
                logger.info(
                    "market_data.sync.completed",
                    symbol=symbol,
                    exchange=exchange,
                    bars_inserted=inserted_count,
                )
            else:
                streak = await self._sync_status_repo.bump_empty_fetch(
                    symbol, exchange, interval,
                )
                emit_no_progress(
                    symbol, exchange, interval,
                    bars_fetched=bars_fetched,
                    filtered_misaligned=filtered_misaligned,
                    filtered_existing=filtered_existing,
                    attempts=getattr(self, "_fetch_attempts", 1),
                    streak=streak,
                    latest_bar=latest_bar,
                )

            return build_success(
                symbol, exchange, interval,
                bars_synced=inserted_count, bars_fetched=bars_fetched,
                filtered_existing=filtered_existing,
                filtered_misaligned=filtered_misaligned,
                total_bars=total_bars, latest_bar=latest_bar,
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
        records, attempts = await fetch_with_retry(
            self.provider, symbol, exchange, interval, n_bars,
        )
        # Exposed to handle() / Phase 2 anomaly log via getattr fallback.
        self._fetch_attempts = attempts
        return records

    async def _persist_bars(self, symbol: str, exchange: str, records: list[Bar]) -> int:
        if not records:
            return 0
        inserted_count = await self._bar_repo.insert_many(records)
        await self._symbol_repo.upsert(Symbol.create(code=symbol, exchange=exchange))
        return inserted_count

    async def _get_bar_stats(
        self, symbol: str, exchange: str, interval: DomainInterval
    ) -> tuple[int, Bar | None]:
        total_bars = await self._bar_repo.count(symbol, exchange, interval)
        latest_bar = await self._bar_repo.get_latest(symbol, exchange, interval)
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

    async def _invalidate_cache(self, symbol: str, exchange: str, interval: DomainInterval) -> None:
        cache_key = build_bar_cache_key(symbol, exchange, interval.value)
        await self._cache.delete_pattern(f"{cache_key}:*")

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
