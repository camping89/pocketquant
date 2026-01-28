"""Handlers for status queries."""

from src.common.constants import COLLECTION_SYNC_STATUS
from src.common.database import Database
from src.common.mediator import Handler
from src.config import Settings
from src.features.market_data.models.ohlcv import Interval, SyncStatus
from src.features.market_data.quote.handler import get_quote_state
from src.features.market_data.status.dto import StatusResult, SyncStatusResult
from src.features.market_data.status.query import (
    GetQuoteServiceStatusQuery,
    GetSymbolSyncStatusQuery,
    GetSyncStatusQuery,
)


class GetSyncStatusHandler(Handler[GetSyncStatusQuery, list[SyncStatusResult]]):
    """Handle getting all sync statuses."""

    async def handle(self, query: GetSyncStatusQuery) -> list[SyncStatusResult]:
        collection = Database.get_collection(COLLECTION_SYNC_STATUS)
        cursor = collection.find()

        statuses = [SyncStatus.from_mongo(doc) async for doc in cursor]

        return [
            SyncStatusResult(
                symbol=s.symbol,
                exchange=s.exchange,
                interval=s.interval,
                status=s.status,
                bar_count=s.bar_count,
                last_sync_at=s.last_sync_at.isoformat() if s.last_sync_at else None,
                last_bar_at=s.last_bar_at.isoformat() if s.last_bar_at else None,
                error_message=s.error_message,
            )
            for s in statuses
        ]


class GetSymbolSyncStatusHandler(
    Handler[GetSymbolSyncStatusQuery, SyncStatusResult]
):
    """Handle getting sync status for a specific symbol."""

    async def handle(self, query: GetSymbolSyncStatusQuery) -> SyncStatusResult:
        collection = Database.get_collection(COLLECTION_SYNC_STATUS)
        interval = Interval(query.interval)

        doc = await collection.find_one(
            {
                "symbol": query.symbol.upper(),
                "exchange": query.exchange.upper(),
                "interval": interval.value,
            }
        )

        if not doc:
            raise ValueError(
                f"No sync status found for {query.symbol}:{query.exchange}"
            )

        status = SyncStatus.from_mongo(doc)

        return SyncStatusResult(
            symbol=status.symbol,
            exchange=status.exchange,
            interval=status.interval,
            status=status.status,
            bar_count=status.bar_count,
            last_sync_at=status.last_sync_at.isoformat() if status.last_sync_at else None,
            last_bar_at=status.last_bar_at.isoformat() if status.last_bar_at else None,
            error_message=status.error_message,
        )


class GetQuoteServiceStatusHandler(
    Handler[GetQuoteServiceStatusQuery, StatusResult]
):
    """Handle getting quote service status."""

    def __init__(self, settings: Settings):
        self.state = get_quote_state(settings)

    async def handle(self, query: GetQuoteServiceStatusQuery) -> StatusResult:
        return StatusResult(
            running=self.state.running and self.state.provider.is_connected(),
            subscription_count=self.state.provider.subscription_count,
            active_symbols=self.state.bar_manager.active_symbols,
        )
