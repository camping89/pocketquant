"""Brokers that declare async fills deliver them into OrderAppService.on_order_update.

Only a broker with ``fills_async = True`` is subscribed; PaperBrokerAdapter
reports fills inline and stays unsubscribed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.brokers.broker_port import IBrokerPort, OrderCallback, TradeCallback
from pocketquant.core.domain.brokers.value_objects import AccountBalance, OrderResult
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderFilledEvent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

_SYM = "BTCUSDT:BINANCE"


class _InMemoryOrderRepo:
    async def save(self, order: OrderAggregate) -> None:
        return None


class _InMemoryPositionRepo:
    async def find_open(self) -> list[PositionAggregate]:
        return []

    async def save(self, position: PositionAggregate) -> None:
        return None


class _AsyncFillBroker(IBrokerPort):
    fills_async = True

    def __init__(self) -> None:
        self.order_callbacks: list[OrderCallback] = []

    @property
    def name(self) -> str:
        return "fake"

    @property
    def is_connected(self) -> bool:
        return True

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def submit_order(self, order: OrderAggregate) -> OrderResult:
        return OrderResult(
            order_id=str(order.id),
            broker_order_id="op1",
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now(UTC),
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        return False

    async def get_positions(self) -> list[PositionAggregate]:
        return []

    async def get_balance(self) -> AccountBalance:
        return AccountBalance(total_equity=0.0, available_balance=0.0)

    async def subscribe_order_updates(self, callback: OrderCallback) -> None:
        self.order_callbacks.append(callback)

    async def unsubscribe_order_updates(self) -> None:
        self.order_callbacks.clear()

    async def subscribe_trades(self, callback: TradeCallback) -> None:
        return None

    async def unsubscribe_trades(self) -> None:
        return None


class _StubFactory:
    def __init__(self, broker: IBrokerPort) -> None:
        self._broker = broker

    def create(self, broker_type: str, config: dict) -> IBrokerPort:
        return self._broker


def _config(broker: str) -> StrategyConfig:
    return StrategyConfig(id="s1", name="s1", symbol=_SYM, interval="1m", broker=broker)


def _engine(
    bus: EventBus, factory: object, orders: OrderAppService, positions
) -> StrategyAppService:
    return StrategyAppService(
        event_bus=bus,
        broker_factory=factory,  # type: ignore[arg-type]
        order_app_service=orders,
        position_app_service=positions,
        risk_check_handler=object(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_async_fill_reaches_order_service_and_opens_position() -> None:
    bus = EventBus()
    filled: list[OrderFilledEvent] = []
    bus.subscribe(OrderFilledEvent, lambda e: filled.append(e))
    orders = OrderAppService(bus, _InMemoryOrderRepo())  # type: ignore[arg-type]
    positions = PositionAppService(bus, _InMemoryPositionRepo())  # type: ignore[arg-type]
    await positions.start()
    broker = _AsyncFillBroker()
    engine = _engine(bus, _StubFactory(broker), orders, positions)
    await engine.load_strategy(_config("fake"))
    order = OrderAggregate.create(
        subscription_id="s1",
        symbol=_SYM,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=2.0,
        price=10.0,
    )
    await orders.submit(order, broker)

    # The stored callback is the order service's handler, so invoke it directly.
    assert broker.order_callbacks == [orders.on_order_update]
    await orders.on_order_update(
        OrderResult(
            order_id=str(order.id),
            broker_order_id="op1",
            status=OrderStatus.FILLED,
            filled_quantity=2.0,
            filled_price=10.0,
        )
    )

    assert len(filled) == 1
    assert positions.get("s1") is not None


@pytest.mark.asyncio
async def test_paper_broker_is_not_subscribed_to_order_updates() -> None:
    bus = EventBus()
    orders = OrderAppService(bus, _InMemoryOrderRepo())  # type: ignore[arg-type]
    positions = PositionAppService(bus, _InMemoryPositionRepo())  # type: ignore[arg-type]
    engine = _engine(bus, BrokerFactory(EventBus()), orders, positions)

    await engine.load_strategy(_config("paper"))

    broker = engine._brokers["s1"]
    assert isinstance(broker, PaperBrokerAdapter)
    assert len(broker._order_callbacks) == 0


def test_only_async_brokers_declare_async_fills() -> None:
    assert IBrokerPort.fills_async is False
    assert PaperBrokerAdapter.fills_async is False
