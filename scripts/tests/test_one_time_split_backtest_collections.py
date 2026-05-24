"""Integration tests for ``one_time_split_backtest_collections`` against a real Mongo.

Spins up a Mongo testcontainer, seeds 3 pre-migration ``backtest_runs`` docs +
1 ``optimization_runs`` doc, runs the migration, asserts new collections,
slim shape, marker, and idempotency (re-run is no-op).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Iterator

import pytest
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from testcontainers.mongodb import MongoDbContainer

from scripts.one_time_split_backtest_collections import MARKER_PATH, run as run_migration


@pytest.fixture(scope="module")
def mongo_container() -> Iterator[MongoDbContainer]:
    with MongoDbContainer("mongo:7.0") as mongo:
        yield mongo


@pytest.fixture
async def db_uri(mongo_container: MongoDbContainer) -> str:
    return mongo_container.get_connection_url()


def _seed_run_completed_full() -> dict:
    """A complete run: 2 fills (entry+exit), 1 closed position."""
    t0 = datetime(2026, 1, 5, 10, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    return {
        "_id": "run-complete-1",
        "strategy_id": "hitnrun",
        "status": "completed",
        "started_at": t0,
        "completed_at": t1,
        "config_snapshot": {"symbol": "BTCUSDT:BINANCE", "interval": "1m"},
        "metrics": {"total_return": 0.1, "cagr": 0.12, "sharpe_ratio": 1.4,
                    "sortino_ratio": 2.0, "max_drawdown": -0.05, "win_rate": 1.0,
                    "profit_factor": 2.0, "total_trades": 1, "winning_trades": 1,
                    "losing_trades": 0, "avg_win": 10.0, "avg_loss": 0.0,
                    "avg_trade_duration_seconds": 3600.0, "total_commission": 0.21},
        "equity_curve": [],
        "trades": [
            {"order_id": "o1", "symbol": "BTCUSDT:BINANCE", "side": "BUY",
             "quantity": 1.0, "price": 100.0, "commission": 0.1, "pnl": 0.0,
             "timestamp": t0, "sl_price": 90, "tp_price": 120},
            {"order_id": "o2", "symbol": "BTCUSDT:BINANCE", "side": "SELL",
             "quantity": 1.0, "price": 110.0, "commission": 0.11, "pnl": 10.0,
             "timestamp": t1},
        ],
        "positions": [
            {"symbol": "BTCUSDT:BINANCE", "direction": "LONG",
             "entry_price": 100.0, "entry_time": t0, "quantity": 1.0,
             "sl_price": 90, "tp_price": 120, "exit_price": 110.0, "exit_time": t1,
             "pnl": 10.0, "commission": 0.21},
        ],
    }


def _seed_run_mixed_open_closed() -> dict:
    """A run with 1 closed + 1 open position."""
    t0 = datetime(2026, 1, 6, 10, tzinfo=UTC)
    return {
        "_id": "run-mixed-1",
        "strategy_id": "hitnrun",
        "status": "completed",
        "started_at": t0,
        "completed_at": t0 + timedelta(hours=2),
        "config_snapshot": {"symbol": "ETHUSDT:BINANCE", "interval": "1m"},
        "metrics": {"total_return": 0.05, "cagr": 0.06, "sharpe_ratio": 0.8,
                    "sortino_ratio": 1.0, "max_drawdown": -0.03, "win_rate": 1.0,
                    "profit_factor": 2.0, "total_trades": 1, "winning_trades": 1,
                    "losing_trades": 0, "avg_win": 5.0, "avg_loss": 0.0,
                    "avg_trade_duration_seconds": 1800.0, "total_commission": 0.3},
        "equity_curve": [],
        "trades": [
            {"order_id": "oA", "symbol": "ETHUSDT:BINANCE", "side": "BUY",
             "quantity": 0.5, "price": 200.0, "commission": 0.1, "pnl": 0.0,
             "timestamp": t0},
        ],
        "positions": [
            {"symbol": "ETHUSDT:BINANCE", "direction": "LONG",
             "entry_price": 200.0, "entry_time": t0, "quantity": 0.5,
             "sl_price": 180, "tp_price": 220,
             "exit_price": 210.0, "exit_time": t0 + timedelta(hours=1),
             "pnl": 5.0, "commission": 0.2},
            {"symbol": "ETHUSDT:BINANCE", "direction": "SHORT",
             "entry_price": 220.0, "entry_time": t0 + timedelta(hours=1),
             "quantity": 0.3, "sl_price": 230, "tp_price": 200,
             "exit_price": None, "exit_time": None,
             "pnl": 0.0, "commission": 0.1},
        ],
    }


def _seed_run_failed_empty() -> dict:
    """A failed run with empty arrays — should still get marker."""
    return {
        "_id": "run-failed-1",
        "strategy_id": "hitnrun",
        "status": "failed",
        "started_at": datetime(2026, 1, 7, tzinfo=UTC),
        "completed_at": datetime(2026, 1, 7, tzinfo=UTC),
        "config_snapshot": {"symbol": "BTCUSDT:BINANCE", "interval": "1m"},
        "metrics": {"total_return": 0.0, "cagr": 0.0, "sharpe_ratio": 0.0,
                    "sortino_ratio": 0.0, "max_drawdown": 0.0, "win_rate": 0.0,
                    "profit_factor": 0.0, "total_trades": 0, "winning_trades": 0,
                    "losing_trades": 0, "avg_win": 0.0, "avg_loss": 0.0,
                    "avg_trade_duration_seconds": None, "total_commission": 0.0},
        "equity_curve": [],
        "trades": [],
        "positions": [],
        "error_message": "boom",
    }


def _seed_optimization_doc() -> dict:
    return {
        "_id": "opt-1",
        "strategy_id": "hitnrun",
        "started_at": datetime(2026, 1, 8, tzinfo=UTC),
        "completed_at": datetime(2026, 1, 8, tzinfo=UTC),
        "config_snapshot": {},
        "target_metric": "sharpe_ratio",
        "total_combinations": 1,
        "completed_combinations": 1,
        "failed_combinations": 0,
        "results": [],
        "best_parameters": {},
        "best_metrics": {"total_return": 0.0, "cagr": 0.0, "sharpe_ratio": 0.0,
                         "sortino_ratio": 0.0, "max_drawdown": 0.0, "win_rate": 0.0,
                         "profit_factor": 0.0, "total_trades": 0, "winning_trades": 0,
                         "losing_trades": 0, "avg_win": 0.0, "avg_loss": 0.0,
                         "avg_trade_duration_seconds": None, "total_commission": 0.0},
        "status": "completed",
    }


async def _seed(uri: str, db_name: str) -> None:
    client = AsyncMongoClient(uri)
    try:
        db = client[db_name]
        await db["backtest_runs"].drop()
        await db["backtest_orders"].drop()
        await db["backtest_trades"].drop()
        await db["optimization_runs"].drop()
        await db["backtest_optimization_runs"].drop()
        await db["backtest_runs"].insert_many(
            [_seed_run_completed_full(), _seed_run_mixed_open_closed(), _seed_run_failed_empty()]
        )
        await db["optimization_runs"].insert_one(_seed_optimization_doc())
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_dry_run_does_not_write(mongo_container: MongoDbContainer) -> None:
    uri = mongo_container.get_connection_url()
    db_name = "pq_dryrun_test"
    await _seed(uri, db_name)

    await run_migration(
        mongo_uri=uri, db_name=db_name,
        dry_run=True, exclude_running=True, validate_only=False,
    )

    client = AsyncMongoClient(uri)
    try:
        db = client[db_name]
        # Dry-run wrote nothing
        assert await db["backtest_orders"].count_documents({}) == 0
        assert await db["backtest_trades"].count_documents({}) == 0
        # Legacy fields still present on original runs
        unmigrated = await db["backtest_runs"].count_documents(
            {MARKER_PATH: {"$exists": False}}
        )
        assert unmigrated == 3
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_real_run_reconstructs_collections(mongo_container: MongoDbContainer) -> None:
    uri = mongo_container.get_connection_url()
    db_name = "pq_realrun_test"
    await _seed(uri, db_name)

    await run_migration(
        mongo_uri=uri, db_name=db_name,
        dry_run=False, exclude_running=True, validate_only=False,
    )

    client = AsyncMongoClient(uri)
    try:
        db = client[db_name]

        # Backups created
        names = await db.list_collection_names()
        assert any(n.startswith("backtest_runs_backup_") for n in names)
        assert any(n.startswith("optimization_runs_backup_") for n in names)

        # Orders: run-complete-1 (2 fills) + run-mixed-1 (1 fill) = 3 total
        assert await db["backtest_orders"].count_documents({}) == 3
        # Trades: 1 (complete) + 1 (mixed closed) = 2 total
        assert await db["backtest_trades"].count_documents({}) == 2
        # All runs marked
        unmigrated = await db["backtest_runs"].count_documents(
            {MARKER_PATH: {"$exists": False}}
        )
        assert unmigrated == 0
        # No legacy fields on any run
        legacy = await db["backtest_runs"].count_documents(
            {"$or": [{"trades": {"$exists": True}}, {"positions": {"$exists": True}}]}
        )
        assert legacy == 0
        # Open positions only on the mixed run (1 open lot)
        mixed = await db["backtest_runs"].find_one({"_id": "run-mixed-1"})
        assert mixed is not None and len(mixed.get("open_positions", [])) == 1
        assert mixed["open_positions"][0]["direction"] == "SHORT"
        # Optimization renamed
        assert "optimization_runs" not in names
        assert "backtest_optimization_runs" in names
        assert await db["backtest_optimization_runs"].count_documents({}) == 1

        # Run-complete-1 trade has correct linkage shape (entry/exit order_id are None per migration loss)
        trade = await db["backtest_trades"].find_one({"run_id": "run-complete-1"})
        assert trade is not None
        assert trade["entry_order_id"] is None
        assert trade["exit_order_id"] is None
        assert trade["pnl"] == 10.0

        # Orders carry the migrated event log (SUBMITTED + FILLED with reason=migrated)
        order = await db["backtest_orders"].find_one({"_id": "o1"})
        assert order is not None
        assert order["status"] == "filled"
        assert len(order["events"]) == 2
        assert order["events"][1]["reason"] == "migrated"
        assert len(order["fills"]) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_rerun_is_noop(mongo_container: MongoDbContainer) -> None:
    uri = mongo_container.get_connection_url()
    db_name = "pq_rerun_test"
    await _seed(uri, db_name)

    # First real run
    await run_migration(
        mongo_uri=uri, db_name=db_name,
        dry_run=False, exclude_running=True, validate_only=False,
    )

    client = AsyncMongoClient(uri)
    try:
        db = client[db_name]
        orders_before = await db["backtest_orders"].count_documents({})
        trades_before = await db["backtest_trades"].count_documents({})

        # Second run — should be no-op (marker present)
        await run_migration(
            mongo_uri=uri, db_name=db_name,
            dry_run=False, exclude_running=True, validate_only=False,
        )

        orders_after = await db["backtest_orders"].count_documents({})
        trades_after = await db["backtest_trades"].count_documents({})
        assert orders_after == orders_before
        assert trades_after == trades_before
    finally:
        await client.close()
