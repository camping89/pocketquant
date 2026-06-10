"""BacktestRepository slim-shape persistence test (post-Phase-4)."""

from __future__ import annotations

from datetime import datetime

import pytest

from pocketquant.core.domain.backtest import BacktestMetrics, BacktestResult, EquityPoint, OpenLot
from pocketquant.core.persistence.mongodb import Database
from pocketquant.core.persistence.repositories.backtest_repository import (
    BacktestRepository,
)

# Mongo strips tz info on roundtrip — naive datetime keeps equality clean.
NOW = datetime(2026, 1, 5, 10, 0, 0)


def _result() -> BacktestResult:
    return BacktestResult(
        id="r1",
        strategy_code="s1",
        config_snapshot={"symbol": "BTC:BIN", "interval": "1m"},
        metrics=BacktestMetrics.empty(),
        equity_curve=[EquityPoint(timestamp=NOW, equity=10_000.0, drawdown=0.0)],
        open_positions=[
            OpenLot(
                symbol="BTC:BIN",
                direction="LONG",
                entry_price=100.0,
                entry_time=NOW,
                quantity=1.0,
                sl_price=90,
                tp_price=120,
                entry_order_id="o1",
                entry_commission_portion=0.1,
            ),
        ],
        started_at=NOW,
        completed_at=NOW,
        status="completed",
        parameters={"lookback": 10},
    )


@pytest.mark.asyncio
async def test_save_writes_slim_doc_without_legacy_arrays(database: Database) -> None:
    repo = BacktestRepository(database)
    await repo.save(_result())
    coll = database.get_collection("backtest_runs")
    doc = await coll.find_one({"_id": "r1"})
    assert doc is not None
    # Slim invariant: NO legacy arrays
    assert "trades" not in doc
    assert "positions" not in doc
    assert "open_positions" in doc
    assert len(doc["open_positions"]) == 1
    assert doc["open_positions"][0]["direction"] == "LONG"


@pytest.mark.asyncio
async def test_roundtrip_preserves_open_positions(database: Database) -> None:
    repo = BacktestRepository(database)
    original = _result()
    await repo.save(original)
    fetched = await repo.get("r1")
    assert fetched is not None
    assert fetched.open_positions == original.open_positions


@pytest.mark.asyncio
async def test_from_mongo_tolerates_legacy_doc_with_trades_positions(database: Database) -> None:
    """Pre-migration docs with legacy trades[]/positions[] must still deserialise."""
    coll = database.get_collection("backtest_runs")
    legacy_doc = {
        "_id": "legacy-1",
        "strategy_code": "s1",
        "config_snapshot": {"symbol": "BTC:BIN", "interval": "1m"},
        "metrics": BacktestMetrics.empty().to_mongo(),
        "equity_curve": [],
        "started_at": NOW,
        "completed_at": NOW,
        "status": "completed",
        # Legacy fields — must be silently ignored by from_mongo.
        "trades": [
            {
                "order_id": "x",
                "symbol": "BTC:BIN",
                "side": "BUY",
                "quantity": 1.0,
                "price": 100.0,
                "commission": 0.1,
                "pnl": 0.0,
                "timestamp": NOW,
            }
        ],
        "positions": [
            {
                "symbol": "BTC:BIN",
                "entry_price": 100.0,
                "entry_time": NOW,
                "quantity": 1.0,
                "sl_price": None,
                "tp_price": None,
                "exit_price": 110.0,
                "exit_time": NOW,
                "pnl": 10.0,
                "commission": 0.21,
                "direction": "LONG",
            }
        ],
    }
    await coll.insert_one(legacy_doc)
    repo = BacktestRepository(database)
    fetched = await repo.get("legacy-1")
    assert fetched is not None
    assert fetched.id == "legacy-1"
    assert fetched.open_positions == []
