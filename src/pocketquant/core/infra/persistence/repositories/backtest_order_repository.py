from __future__ import annotations

from pocketquant.core.common.constants import COLLECTION_BACKTEST_ORDERS
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.order import OrderRecord
from pocketquant.core.infra.persistence.base_repository import SymbolScopedRepository

logger = get_logger(__name__)


class BacktestOrderRepository(SymbolScopedRepository):
    _collection_name = COLLECTION_BACKTEST_ORDERS

    async def save_many(self, orders: list[OrderRecord]) -> None:
        if not orders:
            return
        collection = self._collection()
        # bulk_write via individual replace_one upserts to keep idempotency
        # without surfacing bson BulkWriteError on duplicate _id replays.
        for order in orders:
            await collection.replace_one(
                {"_id": str(order.order_id)}, order.to_mongo(), upsert=True
            )
        logger.debug("backtest_orders_saved", count=len(orders))

    async def get(self, order_id: str) -> OrderRecord | None:
        collection = self._collection()
        doc = await collection.find_one({"_id": order_id})
        return OrderRecord.from_mongo(doc) if doc else None

    async def list_by_run(self, run_id: str) -> list[OrderRecord]:
        collection = self._collection()
        cursor = collection.find({"run_id": run_id}).sort("submitted_at", 1)
        return [OrderRecord.from_mongo(doc) async for doc in cursor]

    async def list_by_strategy_code_status(
        self, strategy_code: str, status: str, limit: int = 100
    ) -> list[OrderRecord]:
        collection = self._collection()
        cursor = (
            collection.find({"strategy_code": strategy_code, "status": status})
            .sort("submitted_at", -1)
            .limit(limit)
        )
        return [OrderRecord.from_mongo(doc) async for doc in cursor]

    async def delete_by_run(self, run_id: str) -> int:
        collection = self._collection()
        result = await collection.delete_many({"run_id": run_id})
        return result.deleted_count

    async def ensure_indexes(self) -> None:
        collection = self._collection()
        await collection.create_index("run_id", name="ix_btorders_run_id")
        await collection.create_index(
            [("strategy_code", 1), ("status", 1)], name="ix_btorders_strategy_code_status"
        )
        await collection.create_index("submitted_at", name="ix_btorders_submitted_at")
        await collection.create_index([("run_id", 1), ("status", 1)], name="ix_btorders_run_status")
        logger.info("backtest_orders_indexes_created")
