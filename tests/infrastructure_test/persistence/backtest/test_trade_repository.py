"""BacktestTradeRepository CRUD + index tests against a real Mongo testcontainer."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pocketquant.core.domain.backtest import Trade
from pocketquant.infrastructure.persistence.mongodb import Database
from pocketquant.infrastructure.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)

# Mongo strips tz info on roundtrip — naive datetime keeps equality clean.
T0 = datetime(2026, 1, 5, 10, 0, 0)


def _trade(
    *,
    trade_id: str,
    run_id: str,
    pnl: float = 10.0,
    direction: str = "LONG",
    strategy_code: str = "s1",
) -> Trade:
    return Trade(
        trade_id=trade_id,
        run_id=run_id,
        strategy_code=strategy_code,
        symbol="BTC:BIN",
        direction=direction,
        entry_order_id="o-entry",
        entry_price=100.0,
        entry_time=T0,
        quantity=1.0,
        exit_order_id="o-exit",
        exit_price=100.0 + pnl,
        exit_time=T0 + timedelta(hours=1),
        sl_price=None,
        tp_price=None,
        pnl=pnl,
        commission=0.21,
        duration_seconds=3600.0,
    )


@pytest.mark.asyncio
async def test_save_and_get_roundtrip(database: Database) -> None:
    repo = BacktestTradeRepository(database)
    t = _trade(trade_id="t1", run_id="r1")
    await repo.save_many([t])
    fetched = await repo.get("t1")
    assert fetched == t


@pytest.mark.asyncio
async def test_list_by_run_chronological(database: Database) -> None:
    repo = BacktestTradeRepository(database)
    older = _trade(trade_id="t1", run_id="r1")
    newer = _trade(trade_id="t2", run_id="r1")
    newer.entry_time = T0 + timedelta(hours=2)
    await repo.save_many([newer, older])
    out = await repo.list_by_run("r1")
    assert [t.trade_id for t in out] == ["t1", "t2"]  # sorted by entry_time asc


@pytest.mark.asyncio
async def test_list_top_pnl_desc_by_default(database: Database) -> None:
    repo = BacktestTradeRepository(database)
    await repo.save_many(
        [
            _trade(trade_id="t1", run_id="r1", pnl=5.0),
            _trade(trade_id="t2", run_id="r1", pnl=20.0),
            _trade(trade_id="t3", run_id="r1", pnl=-10.0),
        ]
    )
    top = await repo.list_top_pnl("s1", top=2)
    assert [t.trade_id for t in top] == ["t2", "t1"]
    bottom = await repo.list_top_pnl("s1", top=2, ascending=True)
    assert [t.trade_id for t in bottom] == ["t3", "t1"]


@pytest.mark.asyncio
async def test_delete_by_run_only_matches(database: Database) -> None:
    repo = BacktestTradeRepository(database)
    await repo.save_many(
        [
            _trade(trade_id="t1", run_id="r1"),
            _trade(trade_id="t2", run_id="r2"),
        ]
    )
    n = await repo.delete_by_run("r1")
    assert n == 1
    assert await repo.get("t1") is None
    assert await repo.get("t2") is not None


@pytest.mark.asyncio
async def test_ensure_indexes_creates_all_five(database: Database) -> None:
    repo = BacktestTradeRepository(database)
    await repo.ensure_indexes()
    coll = database.get_collection("backtest_trades")
    indexes = await coll.index_information()
    expected = {
        "ix_bttrades_run_id",
        "ix_bttrades_strategy_code_direction",
        "ix_bttrades_entry_time",
        "ix_bttrades_pnl",
        "ix_bttrades_run_entry",
    }
    assert expected.issubset(set(indexes))
