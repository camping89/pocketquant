from pocketquant.core.common.constants import build_bar_cache_key
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import SOURCE_BULK_SYNC, Bar
from pocketquant.core.domain.market_data.interfaces import IDataProvider
from pocketquant.core.domain.shared.enums import Interval as DomainInterval
from pocketquant.core.domain.symbol import Symbol
from pocketquant.core.domain.sync_status.services import SyncProgressDecision, SyncProgressTracker
from pocketquant.core.infra.persistence import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.infra.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)
from pocketquant.engine.market_data.sync_dtos import (
    BulkSyncCommand,
    SyncResponse,
    SyncSymbolCommand,
)
from pocketquant.engine.market_data.sync_internals.anomaly_log import emit_no_progress
from pocketquant.engine.market_data.sync_internals.bar_filters import (
    drop_misaligned_bars,
    filter_new_bars,
)
from pocketquant.engine.market_data.sync_internals.provider_fetch import fetch_with_retry
from pocketquant.engine.market_data.sync_internals.responses import build_success

logger = get_logger(__name__)

# Re-export DTOs so callers can import them from this module without knowing about sync_dtos.
__all__ = ["SyncService", "SyncSymbolCommand", "BulkSyncCommand", "SyncResponse"]


class SyncService:
    def __init__(
        self,
        provider: IDataProvider,
        cache: Cache,
        bar_repository: BarRepository,
        symbol_repository: SymbolRepository,
        sync_status_repository: SyncStatusRepository,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._bar_repo = bar_repository
        self._symbol_repo = symbol_repository
        self._sync_status_repo = sync_status_repository

    async def sync_one(self, request: SyncSymbolCommand) -> SyncResponse:
        """Sync OHLCV bars for a single composite symbol."""
        symbol = request.symbol.upper()
        interval = request.interval

        logger.info(
            "market_data.sync.started",
            symbol=symbol,
            interval=interval.value,
            source=request.source,
        )

        await self._sync_status_repo.upsert(symbol, interval, "syncing")

        try:
            records, fetch_attempts = await fetch_with_retry(
                self._provider, symbol, interval, request.n_bars
            )
            bars_fetched = len(records)
            filtered_existing = 0
            filtered_misaligned = 0

            if records:
                # skip_filter=True on repair runs — gaps must fill regardless of existing state.
                if not request.skip_filter:
                    pre = len(records)
                    records = await filter_new_bars(records, symbol, interval, self._bar_repo)
                    filtered_existing = pre - len(records)
                pre_align = len(records)
                records = drop_misaligned_bars(records, interval)
                filtered_misaligned = pre_align - len(records)

            inserted_count = await self._persist_bars(symbol, records, request.source)
            total_bars, latest_bar = await self._get_bar_stats(symbol, interval)

            if bars_fetched == 0 and total_bars == 0:
                return await self._fail(symbol, interval, "No data returned from provider")

            await self._mark_completed(symbol, interval, total_bars, latest_bar)
            await self._invalidate_cache(symbol, interval)

            decision = SyncProgressTracker.decide(inserted_count)
            if decision is SyncProgressDecision.RESET:
                await self._sync_status_repo.reset_empty_fetch(symbol, interval)
                logger.info(
                    "market_data.sync.completed",
                    symbol=symbol,
                    bars_inserted=inserted_count,
                )
            else:
                streak = await self._sync_status_repo.bump_empty_fetch(symbol, interval)
                emit_no_progress(
                    symbol,
                    interval,
                    bars_fetched=bars_fetched,
                    filtered_misaligned=filtered_misaligned,
                    filtered_existing=filtered_existing,
                    attempts=fetch_attempts,
                    streak=streak,
                    latest_bar=latest_bar,
                )

            return build_success(
                symbol,
                interval,
                bars_synced=inserted_count,
                bars_fetched=bars_fetched,
                filtered_existing=filtered_existing,
                filtered_misaligned=filtered_misaligned,
                total_bars=total_bars,
                latest_bar=latest_bar,
            )

        except Exception as e:
            logger.error(
                "market_data.sync.failed",
                symbol=symbol,
                interval=interval.value,
                error=str(e),
            )
            return await self._fail(symbol, interval, str(e))

    async def sync_bulk(self, request: BulkSyncCommand) -> list[SyncResponse]:
        """Sync multiple composite symbols sequentially."""
        results: list[SyncResponse] = []
        for symbol in request.symbols:
            sync_cmd = SyncSymbolCommand(
                symbol=symbol,
                interval=request.interval,
                n_bars=request.n_bars,
                source=SOURCE_BULK_SYNC,
            )
            result = await self.sync_one(sync_cmd)
            results.append(result)
        return results

    # Private helpers

    async def _persist_bars(self, symbol: str, records: list[Bar], source: str) -> int:
        if not records:
            return 0
        inserted_count = await self._bar_repo.insert_many(records, source=source)
        await self._symbol_repo.upsert(Symbol.create(symbol=symbol))
        return inserted_count

    async def _get_bar_stats(self, symbol: str, interval: DomainInterval) -> tuple[int, Bar | None]:
        total_bars = await self._bar_repo.count(symbol, interval)
        latest_bar = await self._bar_repo.get_latest(symbol, interval)
        return total_bars, latest_bar

    async def _mark_completed(
        self, symbol: str, interval: DomainInterval, bar_count: int, latest_bar: Bar | None
    ) -> None:
        await self._sync_status_repo.upsert(
            symbol,
            interval,
            "completed",
            bar_count=bar_count,
            last_bar_at=latest_bar.datetime if latest_bar else None,
        )

    async def _invalidate_cache(self, symbol: str, interval: DomainInterval) -> None:
        cache_key = build_bar_cache_key(symbol, interval.value)
        await self._cache.delete_pattern(f"{cache_key}:*")

    async def _fail(self, symbol: str, interval: DomainInterval, message: str) -> SyncResponse:
        await self._sync_status_repo.upsert(symbol, interval, "error", error_message=message)
        return SyncResponse(
            symbol=symbol,
            interval=interval.value,
            status="error",
            message=message,
            bars_synced=0,
        )
