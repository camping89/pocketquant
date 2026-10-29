from __future__ import annotations

from pocketquant.core.common.constants import COLLECTION_TRADES
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.trading import Trade
from pocketquant.core.infra.persistence.base_repository import SymbolScopedRepository

logger = get_logger(__name__)


class TradeRepository(SymbolScopedRepository):
    _collection_name = COLLECTION_TRADES

    async def save_many(self, trades: list[Trade]) -> None:
        if not trades:
            return
        collection = self._collection()
        for trade in trades:
            await collection.replace_one(
                {"_id": str(trade.trade_id)}, trade.to_mongo(), upsert=True
            )
        logger.debug("trades_saved", count=len(trades))

    # Live trades set run_id to the subscription_id.
    async def list_by_subscription(self, subscription_id: str, limit: int = 500) -> list[Trade]:
        collection = self._collection()
        cursor = collection.find({"run_id": subscription_id}).sort("entry_time", 1).limit(limit)
        return [Trade.from_mongo(doc) async for doc in cursor]

    async def realized_net(self, run_ids: list[str]) -> float:
        cursor = await self._collection().aggregate(
            [
                {"$match": {"run_id": {"$in": run_ids}}},
                {
                    "$group": {
                        "_id": None,
                        "total": {"$sum": {"$subtract": ["$pnl", "$commission"]}},
                    }
                },
            ]
        )
        async for row in cursor:
            return float(row["total"])
        return 0.0

    async def ensure_indexes(self) -> None:
        collection = self._collection()
        await collection.create_index("run_id", name="ix_trades_run_id")
        await collection.create_index("entry_time", name="ix_trades_entry_time")
        await collection.create_index(
            [("run_id", 1), ("entry_time", 1)], name="ix_trades_run_entry"
        )
        logger.info("trades_indexes_created")
