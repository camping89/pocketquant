"""TradeRepository — MongoDB persistence for the live ``trades`` collection.

Stores round-trip ``Trade`` documents emitted by ``LiveTradeCollector`` during
paper/live trading. Live subscriptions reuse the ``Trade`` shape and set
``run_id`` to the ``subscription_id``, so reads scope by subscription.
"""

from __future__ import annotations

from pocketquant.core.common.constants import COLLECTION_TRADES
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.trading import Trade
from pocketquant.core.infra.persistence.base_repository import BaseRepository

logger = get_logger(__name__)


class TradeRepository(BaseRepository):
    _collection_name = COLLECTION_TRADES

    async def save_many(self, trades: list[Trade]) -> None:
        """Upsert a batch of trades keyed by ``trade_id``. Idempotent."""
        if not trades:
            return
        collection = self._collection()
        for trade in trades:
            await collection.replace_one(
                {"_id": str(trade.trade_id)}, trade.to_mongo(), upsert=True
            )
        logger.debug("trades_saved", count=len(trades))

    async def list_by_subscription(self, subscription_id: str, limit: int = 500) -> list[Trade]:
        """Closed trades for one subscription, oldest-first (``run_id`` == sub id)."""
        collection = self._collection()
        cursor = collection.find({"run_id": subscription_id}).sort("entry_time", 1).limit(limit)
        return [Trade.from_mongo(doc) async for doc in cursor]

    async def ensure_indexes(self) -> None:
        collection = self._collection()
        await collection.create_index("run_id", name="ix_trades_run_id")
        await collection.create_index("entry_time", name="ix_trades_entry_time")
        await collection.create_index(
            [("run_id", 1), ("entry_time", 1)], name="ix_trades_run_entry"
        )
        logger.info("trades_indexes_created")
