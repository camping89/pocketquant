"""BacktestTradeRepository — MongoDB persistence for `backtest_trades` collection.

Stores round-trip ``Trade`` documents (entry + exit linked by order IDs).
"""

from __future__ import annotations

from pocketquant.core.common.constants import COLLECTION_BACKTEST_TRADES
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.backtest.value_objects import Trade
from pocketquant.infrastructure.persistence.base_repository import BaseRepository

logger = get_logger(__name__)


class BacktestTradeRepository(BaseRepository):
    _collection_name = COLLECTION_BACKTEST_TRADES

    async def save_many(self, trades: list[Trade]) -> None:
        """Upsert a batch of trades. Idempotent re-runs OK."""
        if not trades:
            return
        collection = self._collection()
        for trade in trades:
            await collection.replace_one({"_id": trade.trade_id}, trade.to_mongo(), upsert=True)
        logger.debug("backtest_trades_saved", count=len(trades))

    async def get(self, trade_id: str) -> Trade | None:
        collection = self._collection()
        doc = await collection.find_one({"_id": trade_id})
        return Trade.from_mongo(doc) if doc else None

    async def list_by_run(self, run_id: str) -> list[Trade]:
        collection = self._collection()
        cursor = collection.find({"run_id": run_id}).sort("entry_time", 1)
        return [Trade.from_mongo(doc) async for doc in cursor]

    async def list_by_strategy_code(self, strategy_code: str, limit: int = 200) -> list[Trade]:
        collection = self._collection()
        cursor = (
            collection.find({"strategy_code": strategy_code}).sort("entry_time", -1).limit(limit)
        )
        return [Trade.from_mongo(doc) async for doc in cursor]

    async def list_top_pnl(
        self, strategy_code: str, top: int = 10, ascending: bool = False
    ) -> list[Trade]:
        """Top biggest winners (default) or losers (ascending=True)."""
        collection = self._collection()
        order = 1 if ascending else -1
        cursor = collection.find({"strategy_code": strategy_code}).sort("pnl", order).limit(top)
        return [Trade.from_mongo(doc) async for doc in cursor]

    async def delete_by_run(self, run_id: str) -> int:
        collection = self._collection()
        result = await collection.delete_many({"run_id": run_id})
        return result.deleted_count

    async def delete_by_strategy_code(self, strategy_code: str) -> int:
        collection = self._collection()
        result = await collection.delete_many({"strategy_code": strategy_code})
        return result.deleted_count

    async def ensure_indexes(self) -> None:
        """Create indexes for per-run drill-down + cross-run analytics."""
        collection = self._collection()
        await collection.create_index("run_id", name="ix_bttrades_run_id")
        await collection.create_index(
            [("strategy_code", 1), ("direction", 1)], name="ix_bttrades_strategy_code_direction"
        )
        await collection.create_index("entry_time", name="ix_bttrades_entry_time")
        await collection.create_index("pnl", name="ix_bttrades_pnl")
        await collection.create_index(
            [("run_id", 1), ("entry_time", 1)], name="ix_bttrades_run_entry"
        )
        logger.info("backtest_trades_indexes_created")
