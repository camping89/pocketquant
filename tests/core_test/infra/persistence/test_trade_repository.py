"""TradeRepository CRUD + index tests against a real Mongo testcontainer.

Live ``trades`` collection: ``run_id`` == ``subscription_id``, read scoped by sub.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import NAMESPACE_OID, UUID, uuid5

import pytest

from pocketquant.core.domain.trading import Trade
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.trade_repository import TradeRepository

# Mongo strips tz info on roundtrip — naive datetime keeps equality clean.
T0 = datetime(2026, 1, 5, 10, 0, 0)


def _tid(name: str) -> str:
    return str(uuid5(NAMESPACE_OID, name))


def _trade(*, trade_id: str, run_id: str, pnl: float = 10.0) -> Trade:
    return Trade(
        trade_id=UUID(_tid(trade_id)),
        run_id=run_id,
        strategy_code="s1",
        symbol="BTC:BIN",
        direction="LONG",
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
async def test_save_and_list_roundtrip(database: Database) -> None:
    repo = TradeRepository(database)
    t = _trade(trade_id="t1", run_id="sub-1")
    await repo.save_many([t])
    out = await repo.list_by_subscription("sub-1")
    assert out == [t]


@pytest.mark.asyncio
async def test_save_many_upsert_is_idempotent(database: Database) -> None:
    repo = TradeRepository(database)
    t = _trade(trade_id="t1", run_id="sub-1")
    await repo.save_many([t])
    await repo.save_many([t])  # re-run must not duplicate
    assert len(await repo.list_by_subscription("sub-1")) == 1


@pytest.mark.asyncio
async def test_list_by_subscription_scopes_and_sorts(database: Database) -> None:
    repo = TradeRepository(database)
    older = _trade(trade_id="t1", run_id="sub-1")
    newer = _trade(trade_id="t2", run_id="sub-1")
    newer.entry_time = T0 + timedelta(hours=2)
    other = _trade(trade_id="t3", run_id="sub-2")
    await repo.save_many([newer, older, other])

    out = await repo.list_by_subscription("sub-1")
    assert [str(t.trade_id) for t in out] == [_tid("t1"), _tid("t2")]  # entry_time asc
    assert await repo.list_by_subscription("missing") == []


@pytest.mark.asyncio
async def test_ensure_indexes_creates_expected(database: Database) -> None:
    repo = TradeRepository(database)
    await repo.ensure_indexes()
    coll = database.get_collection("trades")
    indexes = await coll.index_information()
    expected = {"ix_trades_run_id", "ix_trades_entry_time", "ix_trades_run_entry"}
    assert expected.issubset(set(indexes))
