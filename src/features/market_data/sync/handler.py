"""Handlers for sync commands."""

from datetime import UTC, datetime

from pymongo import UpdateOne

from src.common.cache import Cache
from src.common.constants import (
    COLLECTION_OHLCV,
    COLLECTION_SYMBOLS,
    COLLECTION_SYNC_STATUS,
)
from src.common.database import Database
from src.common.logging import get_logger
from src.common.mediator import Handler
from src.common.messaging import EventBus
from src.domain.ohlcv import OHLCVAggregate
from src.features.market_data.models.ohlcv import OHLCV, Interval, OHLCVCreate
from src.features.market_data.sync.command import BulkSyncCommand, SyncSymbolCommand
from src.features.market_data.sync.dto import SyncResult
from src.infrastructure.tradingview import TradingViewProvider

logger = get_logger(__name__)


class SyncSymbolHandler(Handler[SyncSymbolCommand, SyncResult]):
    """Handle syncing a single symbol."""

    def __init__(self, provider: TradingViewProvider, event_bus: EventBus):
        self.provider = provider
        self.event_bus = event_bus

    async def handle(self, cmd: SyncSymbolCommand) -> SyncResult:
        symbol = cmd.symbol.upper()
        exchange = cmd.exchange.upper()
        interval = Interval(cmd.interval)

        logger.info(
            "market_data.sync.started",
            symbol=symbol,
            exchange=exchange,
            interval=interval.value,
        )

        await self._update_sync_status(symbol, exchange, interval, "syncing")

        try:
            records = await self.provider.fetch_ohlcv(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                n_bars=cmd.n_bars,
            )

            if not records:
                await self._update_sync_status(
                    symbol,
                    exchange,
                    interval,
                    "error",
                    error_message="No data returned from provider",
                )
                return SyncResult(
                    symbol=symbol,
                    exchange=exchange,
                    interval=interval.value,
                    status="error",
                    message="No data returned from provider",
                    bars_synced=0,
                )

            upserted_count = await self._upsert_many(records)
            await self._upsert_symbol(symbol, exchange)

            total_bars = await self._get_bar_count(symbol, exchange, interval)
            latest_bar = await self._get_latest_bar(symbol, exchange, interval)

            await self._update_sync_status(
                symbol,
                exchange,
                interval,
                "completed",
                bar_count=total_bars,
                last_bar_at=latest_bar.datetime if latest_bar else None,
            )

            cache_key = f"ohlcv:{symbol}:{exchange}:{interval.value}"
            await Cache.delete_pattern(f"{cache_key}:*")

            aggregate = OHLCVAggregate(symbol=symbol, exchange=exchange)
            aggregate.record_sync(
                interval=interval,
                bar_count=upserted_count,
                last_bar_time=latest_bar.datetime if latest_bar else datetime.now(UTC),
            )
            await self.event_bus.publish_all(aggregate.get_uncommitted_events())

            result = SyncResult(
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

            await self._update_sync_status(
                symbol, exchange, interval, "error", error_message=error_msg
            )

            return SyncResult(
                symbol=symbol,
                exchange=exchange,
                interval=interval.value,
                status="error",
                message=error_msg,
                bars_synced=0,
            )

    async def _upsert_many(self, records: list[OHLCVCreate]) -> int:
        if not records:
            return 0

        collection = Database.get_collection(COLLECTION_OHLCV)
        operations = []

        for record in records:
            ohlcv = OHLCV(**record.model_dump())
            doc = ohlcv.to_mongo()
            created_at = doc.pop("created_at", None)

            update_ops: dict = {"$set": doc}
            if created_at:
                update_ops["$setOnInsert"] = {"created_at": created_at}

            operations.append(
                UpdateOne(
                    {
                        "symbol": doc["symbol"],
                        "exchange": doc["exchange"],
                        "interval": doc["interval"],
                        "datetime": doc["datetime"],
                    },
                    update_ops,
                    upsert=True,
                )
            )

        result = await collection.bulk_write(operations, ordered=False)
        total = result.upserted_count + result.modified_count

        logger.info(
            "data_sync.upserted",
            upserted_count=result.upserted_count,
            modified_count=result.modified_count,
            total_count=total,
        )

        return total

    async def _update_sync_status(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        status: str,
        bar_count: int | None = None,
        last_bar_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        collection = Database.get_collection(COLLECTION_SYNC_STATUS)

        update_doc: dict = {
            "symbol": symbol.upper(),
            "exchange": exchange.upper(),
            "interval": interval.value,
            "status": status,
            "last_sync_at": datetime.now(UTC),
        }

        if bar_count is not None:
            update_doc["bar_count"] = bar_count
        if last_bar_at is not None:
            update_doc["last_bar_at"] = last_bar_at
        if error_message is not None:
            update_doc["error_message"] = error_message

        await collection.update_one(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "interval": interval.value,
            },
            {"$set": update_doc},
            upsert=True,
        )

    async def _get_bar_count(
        self, symbol: str, exchange: str, interval: Interval
    ) -> int:
        collection = Database.get_collection(COLLECTION_OHLCV)
        return await collection.count_documents(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "interval": interval.value,
            }
        )

    async def _get_latest_bar(
        self, symbol: str, exchange: str, interval: Interval
    ) -> OHLCV | None:
        collection = Database.get_collection(COLLECTION_OHLCV)
        doc = await collection.find_one(
            {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "interval": interval.value,
            },
            sort=[("datetime", -1)],
        )
        return OHLCV.from_mongo(doc) if doc else None

    async def _upsert_symbol(self, symbol: str, exchange: str) -> None:
        collection = Database.get_collection(COLLECTION_SYMBOLS)
        symbol_doc = {
            "symbol": symbol,
            "exchange": exchange,
            "is_active": True,
            "updated_at": datetime.now(UTC),
        }
        await collection.update_one(
            {"symbol": symbol, "exchange": exchange},
            {"$set": symbol_doc, "$setOnInsert": {"created_at": datetime.now(UTC)}},
            upsert=True,
        )


class BulkSyncHandler(Handler[BulkSyncCommand, list[SyncResult]]):
    """Handle syncing multiple symbols."""

    def __init__(self, sync_handler: SyncSymbolHandler):
        self.sync_handler = sync_handler

    async def handle(self, cmd: BulkSyncCommand) -> list[SyncResult]:
        results = []
        for sym in cmd.symbols:
            sync_cmd = SyncSymbolCommand(
                symbol=sym["symbol"],
                exchange=sym["exchange"],
                interval=cmd.interval,
                n_bars=cmd.n_bars,
            )
            result = await self.sync_handler.handle(sync_cmd)
            results.append(result)
        return results
