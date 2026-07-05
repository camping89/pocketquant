"""BacktestRepository slim-shape persistence test (post-Phase-4)."""

from __future__ import annotations

from datetime import datetime

import pytest

from pocketquant.core.common.uuid import generate_id, generate_id_str
from pocketquant.core.domain.backtest import BacktestResult, OpenLot
from pocketquant.core.domain.trading import EquityPoint, PerformanceMetrics
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)

# Mongo strips tz info on roundtrip — naive datetime keeps equality clean.
NOW = datetime(2026, 1, 5, 10, 0, 0)

RUN_ID = generate_id()


def _result() -> BacktestResult:
    return BacktestResult(
        id=RUN_ID,
        strategy_code="s1",
        config_snapshot={"symbol": "BTC:BIN", "interval": "1m"},
        metrics=PerformanceMetrics.empty(),
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
    doc = await coll.find_one({"_id": str(RUN_ID)})
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
    fetched = await repo.get(str(RUN_ID))
    assert fetched is not None
    assert fetched.open_positions == original.open_positions


def _scoped_run(strategy_code: str, symbol: str, interval: str) -> BacktestResult:
    """A finished run carrying top-level symbol/interval for scope-filter tests."""
    run = BacktestResult.started(
        generate_id_str(),
        {"strategy_code": strategy_code, "symbol": symbol, "interval": interval},
    )
    run.status = "finished"
    return run


@pytest.mark.asyncio
async def test_list_by_strategy_code_filters_by_composite_symbol_and_interval(
    database: Database,
) -> None:
    """Scope filter uses the composite symbol (CODE:EXCHANGE), not the bare code."""
    repo = BacktestRepository(database)
    await repo.save(_scoped_run("hitnrun2", "BTCUSDT:BINANCE", "1m"))
    await repo.save(_scoped_run("hitnrun2", "BTCUSDT:BINANCE", "1m"))
    await repo.save(_scoped_run("hitnrun2", "ETHUSDT:BINANCE", "1m"))
    await repo.save(_scoped_run("hitnrun2", "BTCUSDT:BINANCE", "5m"))

    scoped = await repo.list_by_strategy_code(
        "hitnrun2", symbol="BTCUSDT:BINANCE", interval="1m"
    )
    assert len(scoped) == 2
    assert all(r.symbol == "BTCUSDT:BINANCE" and r.interval == "1m" for r in scoped)


@pytest.mark.asyncio
async def test_list_by_strategy_code_without_scope_returns_all(database: Database) -> None:
    """Omitting symbol/interval keeps the original strategy-wide behaviour."""
    repo = BacktestRepository(database)
    await repo.save(_scoped_run("engulfing", "BTCUSDT:BINANCE", "1m"))
    await repo.save(_scoped_run("engulfing", "ETHUSDT:BINANCE", "5m"))

    allruns = await repo.list_by_strategy_code("engulfing")
    assert len(allruns) == 2


@pytest.mark.asyncio
async def test_from_mongo_tolerates_legacy_doc_with_trades_positions(database: Database) -> None:
    """Pre-migration docs with legacy trades[]/positions[] must still deserialise."""
    coll = database.get_collection("backtest_runs")
    legacy_id = generate_id_str()
    legacy_doc = {
        "_id": legacy_id,
        "strategy_code": "s1",
        "config_snapshot": {"symbol": "BTC:BIN", "interval": "1m"},
        "metrics": PerformanceMetrics.empty().to_mongo(),
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
    fetched = await repo.get(legacy_id)
    assert fetched is not None
    assert str(fetched.id) == legacy_id
    assert fetched.open_positions == []
