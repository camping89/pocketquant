"""OrderAppService.submit — immediate MARKET fills publish OrderFilledEvent.

Regression: an immediate broker fill used to call order.fill() on a PENDING
order, violating the PENDING→SUBMITTED→FILLED state machine. The fill raised,
the order was wrongly REJECTED, and the entry OrderFilledEvent never published.
"""

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
from pocketquant.core.infra.brokers.paper.paper_broker import PaperBroker
from pocketquant.engine.app_services.order_app_service import OrderAppService

_SYM = "BTCUSDT:BINANCE"


class _InMemoryOrderRepo:
    def __init__(self) -> None:
        self._items: dict[str, OrderAggregate] = {}

    async def save(self, order: OrderAggregate) -> None:
        self._items[str(order.id)] = order

    async def get(self, order_id: str) -> OrderAggregate | None:
        return self._items.get(order_id)

    async def find_pending(self, limit: int = 500) -> list[OrderAggregate]:
        return []


async def _wired() -> tuple[OrderAppService, PaperBroker, list[OrderFilledEvent]]:
    bus = EventBus()
    events: list[OrderFilledEvent] = []
    bus.subscribe(OrderFilledEvent, lambda e: events.append(e))
    svc = OrderAppService(bus, _InMemoryOrderRepo())  # pyright: ignore[reportArgumentType]
    broker = PaperBroker(initial_balance=100_000.0, slippage_percent=0.0, fill_delay_ms=0)
    await broker.connect()
    broker.set_current_price(_SYM, 100.0)
    return svc, broker, events


def _market(side: OrderSide) -> OrderAggregate:
    return OrderAggregate.create(
        subscription_id="s1",
        symbol=_SYM,
        side=side,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=100.0,
    )


@pytest.mark.asyncio
async def test_immediate_market_fill_returns_filled_and_publishes_event() -> None:
    svc, broker, events = await _wired()

    result = await svc.submit(_market(OrderSide.BUY), broker)

    assert result.status == OrderStatus.FILLED
    assert len(events) == 1
    ev = events[0]
    assert ev.subscription_id == "s1"
    assert ev.side == OrderSide.BUY
    assert ev.filled_price == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_filled_order_tracked_not_pending() -> None:
    svc, broker, _ = await _wired()
    order = _market(OrderSide.BUY)

    await svc.submit(order, broker)

    assert svc.get_order(str(order.id)) is order
    assert order.status == OrderStatus.FILLED
    assert order not in svc.get_pending_orders()
