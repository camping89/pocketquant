"""BacktestOrderRepository CRUD + index tests against a real Mongo testcontainer."""

from __future__ import annotations

from datetime import datetime

import pytest

from pocketquant.core.domain.backtest import Fill, Order
from pocketquant.core.domain.brokers.events import OrderEvent
from pocketquant.core.domain.order import OrderSide, OrderStatus, OrderType
from pocketquant.core.persistence.mongodb import Database
from pocketquant.core.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)

# Mongo strips tz info on roundtrip (naive UTC) — use naive to keep equality clean.
NOW = datetime(2026, 1, 5, 10, 0, 0)


def _make_order(
    *,
    order_id: str,
    run_id: str,
    strategy_code: str = "s1",
    status: OrderStatus = OrderStatus.FILLED,
) -> Order:
    fill = Fill(
        fill_id=f"f-{order_id}",
        order_id=order_id,
        symbol="BTC:BIN",
        side=OrderSide.BUY,
        quantity=1.0,
        price=100.0,
        commission=0.1,
        slippage=0.0,
        timestamp=NOW,
    )
    events = [
        OrderEvent(
            timestamp=NOW, from_status=None, to_status=OrderStatus.SUBMITTED, reason="submit"
        ),
        OrderEvent(
            timestamp=NOW,
            from_status=OrderStatus.SUBMITTED,
            to_status=status,
            reason="market_fill" if status == OrderStatus.FILLED else "end_of_run",
        ),
    ]
    return Order(
        order_id=order_id,
        run_id=run_id,
        strategy_code=strategy_code,
        symbol="BTC:BIN",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=None,
        sl_price=None,
        tp_price=None,
        status=status,
        submitted_at=NOW,
        last_updated_at=NOW,
        events=events,
        fills=[fill] if status == OrderStatus.FILLED else [],
    )


@pytest.mark.asyncio
async def test_save_and_get_roundtrip(database: Database) -> None:
    repo = BacktestOrderRepository(database)
    o = _make_order(order_id="o1", run_id="r1")
    await repo.save_many([o])
    fetched = await repo.get("o1")
    assert fetched == o


@pytest.mark.asyncio
async def test_save_many_empty_noop(database: Database) -> None:
    repo = BacktestOrderRepository(database)
    await repo.save_many([])  # must not raise
    assert await repo.get("missing") is None


@pytest.mark.asyncio
async def test_save_many_is_idempotent_upsert(database: Database) -> None:
    repo = BacktestOrderRepository(database)
    o = _make_order(order_id="o1", run_id="r1")
    await repo.save_many([o])
    # Same id again — replace_one upsert, no duplicate key error.
    await repo.save_many([o])
    coll = database.get_collection("backtest_orders")
    assert await coll.count_documents({"_id": "o1"}) == 1


@pytest.mark.asyncio
async def test_list_by_run_returns_only_matching(database: Database) -> None:
    repo = BacktestOrderRepository(database)
    await repo.save_many(
        [
            _make_order(order_id="o1", run_id="r1"),
            _make_order(order_id="o2", run_id="r1"),
            _make_order(order_id="o3", run_id="r2"),
        ]
    )
    runs = await repo.list_by_run("r1")
    assert {o.order_id for o in runs} == {"o1", "o2"}


@pytest.mark.asyncio
async def test_list_by_strategy_status_filters(database: Database) -> None:
    repo = BacktestOrderRepository(database)
    await repo.save_many(
        [
            _make_order(order_id="o1", run_id="r1", strategy_code="A", status=OrderStatus.FILLED),
            _make_order(order_id="o2", run_id="r1", strategy_code="A", status=OrderStatus.EXPIRED),
            _make_order(order_id="o3", run_id="r1", strategy_code="B", status=OrderStatus.FILLED),
        ]
    )
    expired = await repo.list_by_strategy_code_status("A", "expired")
    assert [o.order_id for o in expired] == ["o2"]


@pytest.mark.asyncio
async def test_delete_by_run_cascades_only_matching(database: Database) -> None:
    repo = BacktestOrderRepository(database)
    await repo.save_many(
        [
            _make_order(order_id="o1", run_id="r1"),
            _make_order(order_id="o2", run_id="r2"),
        ]
    )
    n = await repo.delete_by_run("r1")
    assert n == 1
    assert await repo.get("o1") is None
    assert await repo.get("o2") is not None


@pytest.mark.asyncio
async def test_ensure_indexes_creates_all_four(database: Database) -> None:
    repo = BacktestOrderRepository(database)
    await repo.ensure_indexes()
    coll = database.get_collection("backtest_orders")
    indexes = await coll.index_information()
    expected = {
        "ix_btorders_run_id",
        "ix_btorders_strategy_code_status",
        "ix_btorders_submitted_at",
        "ix_btorders_run_status",
    }
    assert expected.issubset(set(indexes))
