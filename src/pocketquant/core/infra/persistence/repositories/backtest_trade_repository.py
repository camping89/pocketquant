"""BacktestTradeRepository — MongoDB persistence for `backtest_trades` collection.

Stores round-trip ``Trade`` documents (entry + exit linked by order IDs).
"""

from __future__ import annotations

from pocketquant.core.common.constants import COLLECTION_BACKTEST_TRADES
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.backtest.value_objects import Trade
from pocketquant.core.infra.persistence.base_repository import BaseRepository

logger = get_logger(__name__)


class BacktestTradeRepository(BaseRepository):
    _collection_name = COLLECTION_BACKTEST_TRADES

    async def save_many(self, trades: list[Trade]) -> None:
        """Upsert a batch of trades. Idempotent re-runs OK."""
        if not trades:
            return
        collection = self._collection()
        for trade in trades:
            await collection.replace_one(
                {"_id": str(trade.trade_id)}, trade.to_mongo(), upsert=True
            )
        logger.debug("backtest_trades_saved", count=len(trades))

    async def get(self, trade_id: str) -> Trade | None:
        collection = self._collection()
        doc = await collection.find_one({"_id": trade_id})
        return Trade.from_mongo(doc) if doc else None

    async def list_by_run(self, run_id: str) -> list[Trade]:
        collection = self._collection()
        cursor = collection.find({"run_id": run_id}).sort("entry_time", 1)
        return [Trade.from_mongo(doc) async for doc in cursor]

    # Sort keys the paged reader accepts, mapped to their Mongo field. ``status``
    # has no stored column — closed trades all carry an exit, so it sorts by
    # ``exit_time`` as a stable proxy.
    _SORT_FIELDS = {
        "entry_time": "entry_time",
        "pnl": "pnl",
        "quantity": "quantity",
        "duration_seconds": "duration_seconds",
        "entry_price": "entry_price",
        "exit_price": "exit_price",
        "commission": "commission",
        "direction": "direction",
        "status": "exit_time",
    }

    @staticmethod
    def _pnl_filter_clause(pnl_filter: str | None) -> dict:
        if pnl_filter == "wins":
            return {"pnl": {"$gt": 0}}
        if pnl_filter == "losses":
            return {"pnl": {"$lt": 0}}
        return {}

    async def list_by_run_paged(
        self,
        run_id: str,
        *,
        limit: int,
        sort_key: str = "entry_time",
        sort_dir: str = "desc",
        pnl_filter: str | None = None,
        cursor_value: object | None = None,
        cursor_id: str | None = None,
    ) -> tuple[list[Trade], bool]:
        """Keyset page of closed trades for a run.

        Ordered by ``(sort_key, _id)`` so ties on the sort field never drop or
        duplicate a row across pages. Fetches ``limit + 1`` docs; the extra one
        (if present) only signals ``has_more`` and is trimmed from the result.
        Returns ``(trades, has_more)``.
        """
        field = self._SORT_FIELDS.get(sort_key, "entry_time")
        direction = -1 if sort_dir == "desc" else 1
        op = "$lt" if direction == -1 else "$gt"

        query: dict = {"run_id": run_id, **self._pnl_filter_clause(pnl_filter)}
        if cursor_value is not None and cursor_id is not None:
            # (field {op} value) OR (field == value AND _id {op} id) — the _id
            # tie-break keeps ordering total when the sort field repeats.
            query = {
                "$and": [
                    query,
                    {
                        "$or": [
                            {field: {op: cursor_value}},
                            {"$and": [{field: cursor_value}, {"_id": {op: cursor_id}}]},
                        ]
                    },
                ]
            }

        collection = self._collection()
        # Only (run_id, entry_time) and (run_id, pnl) are indexed for sorting;
        # the other columns fall back to an in-memory sort. allow_disk_use keeps
        # that from aborting past Mongo's 32MB sort cap on a large run.
        cursor = (
            collection.find(query)
            .sort([(field, direction), ("_id", direction)])
            .limit(limit + 1)
            .allow_disk_use(True)
        )
        docs = [doc async for doc in cursor]
        has_more = len(docs) > limit
        return [Trade.from_mongo(d) for d in docs[:limit]], has_more

    async def count_by_run(self, run_id: str, pnl_filter: str | None = None) -> int:
        collection = self._collection()
        return await collection.count_documents(
            {"run_id": run_id, **self._pnl_filter_clause(pnl_filter)}
        )

    async def sum_pnl_by_run(self, run_id: str, pnl_filter: str | None = None) -> float:
        """Total PnL over the full (filtered) set — the table footer's aggregate,
        computed server-side so it reflects every trade, not just loaded pages."""
        collection = self._collection()
        pipeline = [
            {"$match": {"run_id": run_id, **self._pnl_filter_clause(pnl_filter)}},
            {"$group": {"_id": None, "total": {"$sum": "$pnl"}}},
        ]
        cursor = await collection.aggregate(pipeline)
        async for row in cursor:
            return float(row["total"])
        return 0.0

    async def list_markers_by_run(self, run_id: str) -> list[dict]:
        """Lite projection for chart arrows — one row per trade, chronological.

        Avoids loading full trade docs just to place BUY/SELL markers.
        """
        collection = self._collection()
        cursor = (
            collection.find(
                {"run_id": run_id},
                {"_id": 1, "entry_time": 1, "exit_time": 1, "direction": 1},
            ).sort("entry_time", 1)
        )
        return [doc async for doc in cursor]

    async def list_by_strategy_code(self, strategy_code: str, limit: int = 200) -> list[Trade]:
        collection = self._collection()
        cursor = (
            collection.find({"strategy_code": strategy_code}).sort("entry_time", -1).limit(limit)
        )
        return [Trade.from_mongo(doc) async for doc in cursor]

    async def list_top_pnl(
        self, strategy_code: str, top: int = 10, ascending: bool = False
    ) -> list[Trade]:
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
        # Keyset paging by pnl (pairs with the wins/losses filter); the default
        # entry_time sort rides ix_bttrades_run_entry above.
        await collection.create_index(
            [("run_id", 1), ("pnl", 1)], name="ix_bttrades_run_pnl"
        )
        logger.info("backtest_trades_indexes_created")
