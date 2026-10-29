"""A clamped Exness size is normalized before the order exists, so its fill opens a position.

``OrderAggregate.fill`` raises unless the fill quantity equals the order
quantity; normalizing in the engine before order creation keeps the two equal
when the adapter clamps 7.9 units (0.079 lots) down to the 0.01-lot minimum.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderStatus, OrderType
from pocketquant.core.infra.brokers.exness.exness_broker_adapter import ExnessBrokerAdapter
from pocketquant.core.infra.brokers.exness.exness_safeguards import Safeguards
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService
from tests.core_test.infra.brokers.exness.test_exness_broker_adapter import (
    _FakeClient,
    _PauseStore,
)

pytestmark = pytest.mark.integration

SYMBOL = "XAUUSD:EXNESS"


@pytest.fixture
async def db(settings):
    database = Database()
    await database.connect(settings)
    for coll in ("orders", "positions"):
        await database.get_collection(coll).drop()
    yield database
    await database.disconnect()


async def test_clamped_size_fills_into_a_matching_position(db: Database) -> None:
    bus = EventBus()
    orders = OrderAppService(bus, OrderRepository(db))
    positions = PositionAppService(bus, PositionRepository(db))
    await positions.start()
    broker = ExnessBrokerAdapter(
        _FakeClient(),  # type: ignore[arg-type]
        bus,
        PositionRepository(db),
        Safeguards(
            live_trading=True, daily_loss_cap=50.0, max_lots=None, leverage=1.0, risk_per_trade=0.02
        ),
        _PauseStore(),  # type: ignore[arg-type]
    )
    await broker._on_event({"event_type": "trading_state_snapshot", "payload": {"positions": []}})
    await broker.subscribe_order_updates(orders.on_order_update)

    size = await broker.normalize_quantity(SYMBOL, 7.9)
    assert size is not None
    order = OrderAggregate.create(
        subscription_id="sub-exness",
        symbol=SYMBOL,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=size,
        price=2345.0,
        sl_price=2300.0,
    )
    await orders.submit(order, broker)
    await broker._on_event(
        {
            "event_type": "transaction_event",
            "operation_id": "op1",
            "client_request_id": str(order.id),
            "status": "success",
            "payload": {
                "deals": [
                    {
                        "deal_id": "d1",
                        "type": "open",
                        "volume": "0.01",
                        "price": "2345.100",
                        "position_id": "p1",
                        "direction": "buy",
                        "create_time": datetime.now(UTC).isoformat(),
                    }
                ]
            },
        }
    )

    assert size == 1.0
    assert order.status == OrderStatus.FILLED
    position = positions.get(order.subscription_id)
    assert position is not None
    assert position.quantity == 1.0
