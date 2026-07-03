"""BacktestTradeRepository CRUD + index tests against a real Mongo testcontainer."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import NAMESPACE_OID, UUID, uuid5

import pytest

from pocketquant.core.domain.backtest import Trade
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)

# Mongo strips tz info on roundtrip — naive datetime keeps equality clean.
T0 = datetime(2026, 1, 5, 10, 0, 0)


def _tid(name: str) -> str:
    """Deterministic uuid string for a short test trade handle (PKs are UUIDs now)."""
    return str(uuid5(NAMESPACE_OID, name))


def _trade(
    *,
    trade_id: str,
    run_id: str,
    pnl: float = 10.0,
    direction: str = "LONG",
    strategy_code: str = "s1",
) -> Trade:
    return Trade(
        trade_id=UUID(_tid(trade_id)),
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
    fetched = await repo.get(_tid("t1"))
    assert fetched == t


@pytest.mark.asyncio
async def test_list_by_run_chronological(database: Database) -> None:
    repo = BacktestTradeRepository(database)
    older = _trade(trade_id="t1", run_id="r1")
    newer = _trade(trade_id="t2", run_id="r1")
    newer.entry_time = T0 + timedelta(hours=2)
    await repo.save_many([newer, older])
    out = await repo.list_by_run("r1")
    assert [str(t.trade_id) for t in out] == [_tid("t1"), _tid("t2")]  # sorted by entry_time asc


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
    assert [str(t.trade_id) for t in top] == [_tid("t2"), _tid("t1")]
    bottom = await repo.list_top_pnl("s1", top=2, ascending=True)
    assert [str(t.trade_id) for t in bottom] == [_tid("t3"), _tid("t1")]


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
    assert await repo.get(_tid("t1")) is None
    assert await repo.get(_tid("t2")) is not None


@pytest.mark.asyncio
async def test_ensure_indexes_creates_expected(database: Database) -> None:
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
        "ix_bttrades_run_pnl",
    }
    assert expected.issubset(set(indexes))


@pytest.mark.asyncio
async def test_paged_walks_all_trades_without_gaps(database: Database) -> None:
    repo = BacktestTradeRepository(database)
    trades = [_trade(trade_id=f"t{i}", run_id="r1", pnl=float(i)) for i in range(5)]
    for i, t in enumerate(trades):
        t.entry_time = T0 + timedelta(hours=i)
    await repo.save_many(trades)

    seen: list[str] = []
    cursor_value: object | None = None
    cursor_id: str | None = None
    for _ in range(10):  # generous bound; loop breaks on has_more == False
        page, has_more = await repo.list_by_run_paged(
            "r1",
            limit=2,
            sort_key="entry_time",
            sort_dir="asc",
            cursor_value=cursor_value,
            cursor_id=cursor_id,
        )
        seen.extend(str(t.trade_id) for t in page)
        if not has_more or not page:
            break
        cursor_value = page[-1].entry_time
        cursor_id = str(page[-1].trade_id)

    expected = [str(t.trade_id) for t in trades]  # entry_time asc == insertion order
    assert seen == expected
    assert len(seen) == len(set(seen))  # no duplicates across pages


@pytest.mark.asyncio
async def test_paged_keyset_stable_on_equal_sort_value(database: Database) -> None:
    # All trades share entry_time; only the _id tie-break keeps ordering total.
    repo = BacktestTradeRepository(database)
    trades = [_trade(trade_id=f"t{i}", run_id="r1", pnl=1.0) for i in range(4)]
    await repo.save_many(trades)

    first, has_more = await repo.list_by_run_paged(
        "r1", limit=2, sort_key="entry_time", sort_dir="asc"
    )
    assert has_more
    second, _ = await repo.list_by_run_paged(
        "r1",
        limit=2,
        sort_key="entry_time",
        sort_dir="asc",
        cursor_value=first[-1].entry_time,
        cursor_id=str(first[-1].trade_id),
    )
    ids = [str(t.trade_id) for t in first + second]
    assert len(ids) == 4
    assert len(set(ids)) == 4  # no row seen twice, none skipped


@pytest.mark.asyncio
async def test_paged_wins_filter(database: Database) -> None:
    repo = BacktestTradeRepository(database)
    await repo.save_many(
        [
            _trade(trade_id="t1", run_id="r1", pnl=5.0),
            _trade(trade_id="t2", run_id="r1", pnl=-3.0),
            _trade(trade_id="t3", run_id="r1", pnl=8.0),
        ]
    )
    wins, _ = await repo.list_by_run_paged("r1", limit=10, pnl_filter="wins")
    assert {str(t.trade_id) for t in wins} == {_tid("t1"), _tid("t3")}
    assert await repo.count_by_run("r1", "wins") == 2
    assert await repo.count_by_run("r1", "losses") == 1
    assert await repo.count_by_run("r1") == 3


@pytest.mark.asyncio
async def test_sum_pnl_by_run(database: Database) -> None:
    repo = BacktestTradeRepository(database)
    await repo.save_many(
        [
            _trade(trade_id="t1", run_id="r1", pnl=5.0),
            _trade(trade_id="t2", run_id="r1", pnl=-3.0),
            _trade(trade_id="t3", run_id="r2", pnl=99.0),
        ]
    )
    assert await repo.sum_pnl_by_run("r1") == 2.0
    assert await repo.sum_pnl_by_run("r1", "wins") == 5.0
    assert await repo.sum_pnl_by_run("missing") == 0.0


@pytest.mark.asyncio
async def test_markers_projection_chronological(database: Database) -> None:
    repo = BacktestTradeRepository(database)
    older = _trade(trade_id="t1", run_id="r1")
    newer = _trade(trade_id="t2", run_id="r1")
    newer.entry_time = T0 + timedelta(hours=2)
    await repo.save_many([newer, older])
    markers = await repo.list_markers_by_run("r1")
    assert [m["_id"] for m in markers] == [_tid("t1"), _tid("t2")]
    # Projection carries the box fields (chart click-to-select needs them) on top
    # of the timing/direction used for BUY/SELL arrows.
    assert set(markers[0].keys()) == {
        "_id",
        "entry_time",
        "exit_time",
        "direction",
        "entry_price",
        "exit_price",
        "sl_price",
        "tp_price",
        "quantity",
        "pnl",
        "commission",
    }
    assert markers[0]["entry_price"] == 100.0
    assert markers[0]["pnl"] == 10.0
