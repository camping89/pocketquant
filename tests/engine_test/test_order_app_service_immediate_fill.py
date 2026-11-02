# Regression: an immediate broker fill called order.fill() on a PENDING order, violating the
# PENDING -> SUBMITTED -> FILLED state machine. The fill raised, the order was wrongly
# REJECTED, and the entry OrderFilledEvent never published.

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


async def _wired() -> tuple[OrderAppService, PaperBrokerAdapter, list[OrderFilledEvent]]:
    bus = EventBus()
    events: list[OrderFilledEvent] = []
    bus.subscribe(OrderFilledEvent, lambda e: events.append(e))
    svc = OrderAppService(bus, _InMemoryOrderRepo())  # pyright: ignore[reportArgumentType]
    broker = PaperBrokerAdapter(initial_balance=100_000.0, slippage_percent=0.0, fill_delay_ms=0)
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

    assert order.status == OrderStatus.FILLED
    assert str(order.id) not in svc._pending


@pytest.mark.asyncio
async def test_failing_fill_handler_keeps_the_order_filled() -> None:
    svc, broker, events = await _wired()

    def _boom(_: OrderFilledEvent) -> None:
        raise RuntimeError("mirror save failed")

    svc._event_bus.subscribe(OrderFilledEvent, _boom)
    order = _market(OrderSide.BUY)

    result = await svc.submit(order, broker)

    assert result.status == OrderStatus.FILLED
    assert order.status == OrderStatus.FILLED
    assert len(events) == 1


@pytest.mark.asyncio
async def test_a_wired_paper_fill_publishes_one_fill_event() -> None:
    svc, broker, events = await _wired()
    await broker.subscribe_order_updates(svc.on_order_update)

    result = await svc.submit(_market(OrderSide.BUY), broker)

    assert result.status == OrderStatus.FILLED
    assert len(events) == 1


@pytest.mark.asyncio
async def test_pending_stop_and_cancel() -> None:
    svc, _, _ = await _wired()
    order = OrderAggregate.create(
        subscription_id="s1",
        symbol=_SYM,
        side=OrderSide.BUY,
        order_type=OrderType.STOP_MARKET,
        quantity=1.0,
        stop_price=101.0,
    )
    order.submit("b1")
    svc._pending[str(order.id)] = order

    assert svc.pending_stop("s1") is order

    await svc.cancel(order)

    assert order.status == OrderStatus.CANCELLED
    assert await svc._order_repo.get(str(order.id)) is order
    assert svc.pending_stop("s1") is None
