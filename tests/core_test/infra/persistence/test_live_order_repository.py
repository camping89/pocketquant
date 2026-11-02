from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def repo(settings):
    db = Database()
    await db.connect(settings)
    await db.get_collection(OrderRepository._collection_name).drop()
    r = OrderRepository(db)
    await r.ensure_indexes()
    yield r
    await db.disconnect()


def _order(subscription_id: str, created_at: datetime) -> OrderAggregate:
    order = OrderAggregate.create(
        subscription_id=subscription_id,
        symbol="BTCUSDT:BINANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=100.0,
    )
    order.created_at = created_at
    return order


@pytest.mark.asyncio
async def test_list_by_subscription_returns_newest_first_up_to_limit(repo):
    t0 = datetime(2026, 1, 5, 10, tzinfo=UTC)
    for i in range(4):
        await repo.save(_order("sub-a", t0 + timedelta(minutes=i)))
    await repo.save(_order("sub-b", t0 + timedelta(minutes=9)))

    found = await repo.list_by_subscription("sub-a", 3)

    assert [o.created_at for o in found] == [t0 + timedelta(minutes=m) for m in (3, 2, 1)]
