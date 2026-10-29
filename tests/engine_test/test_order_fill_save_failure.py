from __future__ import annotations

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderFilledEvent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.execution.order_app_service import OrderAppService


class _FailingRepo:
    async def save(self, order: OrderAggregate) -> None:
        if order.status == OrderStatus.FILLED:
            raise RuntimeError("mongo down")


@pytest.mark.asyncio
async def test_a_failed_save_after_a_fill_still_publishes_the_fill() -> None:
    bus = EventBus()
    fills: list[OrderFilledEvent] = []

    async def on_fill(event: OrderFilledEvent) -> None:
        fills.append(event)

    bus.subscribe(OrderFilledEvent, on_fill)
    broker = PaperBrokerAdapter(fill_delay_ms=0, event_bus=bus)
    await broker.connect()
    service = OrderAppService(bus, _FailingRepo())  # type: ignore[arg-type]
    order = OrderAggregate.create(
        subscription_id="a",
        symbol="BTCUSDT:BINANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=100.0,
        sl_price=90.0,
    )

    await service.submit(order, broker)

    assert [f.order_id for f in fills] == [str(order.id)]
