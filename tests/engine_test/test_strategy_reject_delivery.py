# hitnrun2 arms _open_direction when it emits a signal and clears it only on an opposite
# fill, so a signal that never filled used to silence it for good.

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.brokers.value_objects import AccountBalance, OrderResult
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderCancelledEvent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from pocketquant.core.domain.risk import PositionCalculation, PositionCalculatorDomainService
from pocketquant.core.domain.strategy.services.hitnrun2_strategy_service import (
    HitNRun2StrategyService,
)
from pocketquant.core.domain.strategy.value_objects import Direction, Signal, StrategyConfig
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.engine.backtest.backtest_sandbox_app_service import (
    Continuous24x7CalendarFactory,
    NoClosedTrades,
    NoStoredBars,
)
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

_SYM = "BTCUSDT:BINANCE"
_NOW = datetime(2026, 10, 1, tzinfo=UTC)


class _InMemoryOrderRepo:
    def __init__(self) -> None:
        self._items: dict[str, OrderAggregate] = {}

    async def save(self, order: OrderAggregate) -> None:
        self._items[str(order.id)] = order


class _NoPositions:
    def get(self, strategy_id: str) -> None:
        return None


class _Risk:
    def __init__(self, valid: bool, reason: str = "") -> None:
        self._result = (valid, reason)

    def validate(self, *args: object) -> tuple[bool, str]:
        return self._result


class _FakeBroker:
    fills_async = False

    def __init__(self, status: OrderStatus, normalized: float | None = 1.0) -> None:
        self._status = status
        self._normalized = normalized
        self.submitted: list[OrderAggregate] = []

    async def get_balance(self) -> AccountBalance:
        return AccountBalance(total_equity=100_000.0, available_balance=100_000.0)

    async def normalize_quantity(self, symbol: str, quantity: float) -> float | None:
        return self._normalized

    async def submit_order(
        self, order: OrderAggregate, *, deadline: datetime | None = None
    ) -> OrderResult:
        self.submitted.append(order)
        return OrderResult(
            order_id=str(order.id),
            broker_order_id="",
            status=self._status,
            error_message="venue says no" if self._status == OrderStatus.REJECTED else None,
        )


def _config() -> StrategyConfig:
    return StrategyConfig(id="s1", name="s1", symbol=_SYM, interval="1m")


def _signal() -> Signal:
    return Signal(
        symbol=_SYM,
        direction=Direction.LONG,
        confidence=1.0,
        timestamp=_NOW,
        subscription_id="s1",
        stop_loss_price=99.0,
    )


def _engine(risk: _Risk, bus: EventBus | None = None, orders=None) -> StrategyAppService:
    bus = bus or EventBus()
    return StrategyAppService(
        event_bus=bus,
        broker_factory=BrokerFactory(EventBus(), safeguards_repository=AsyncMock()),
        order_app_service=orders or OrderAppService(bus, _InMemoryOrderRepo()),  # type: ignore[arg-type]
        position_app_service=_NoPositions(),  # type: ignore[arg-type]
        risk_check_handler=risk,  # type: ignore[arg-type]
        bar_repository=NoStoredBars(),  # type: ignore[arg-type]
        calendar_factory=Continuous24x7CalendarFactory(),  # type: ignore[arg-type]
        trade_repository=NoClosedTrades(),  # type: ignore[arg-type]
        default_broker_config={"initial_balance": 100_000.0},
    )


async def _armed(engine: StrategyAppService) -> HitNRun2StrategyService:
    await engine.load_strategy(_config(), HitNRun2StrategyService)
    await engine.start_strategy("s1")
    strategy = engine._strategies["s1"]
    assert isinstance(strategy, HitNRun2StrategyService)
    strategy._open_direction = Direction.LONG
    return strategy


@pytest.mark.asyncio
async def test_hitnrun2_on_order_rejected_clears_open_direction() -> None:
    strategy = HitNRun2StrategyService(_config())
    strategy._open_direction = Direction.SHORT

    await strategy.on_order_rejected("x")

    assert strategy._open_direction is None


@pytest.mark.asyncio
async def test_risk_rejection_on_paper_rearms_strategy_without_order() -> None:
    orders = AsyncMock()
    engine = _engine(_Risk(False, "max exposure"), orders=orders)
    strategy = await _armed(engine)
    broker = engine._brokers["s1"]
    broker.submit_order = AsyncMock()  # type: ignore[method-assign]

    await engine._process_signal(strategy, _signal(), BarCompletedEvent(close=100.0), _NOW, _NOW)

    broker.submit_order.assert_not_called()
    orders.submit.assert_not_called()
    assert strategy._open_direction is None


@pytest.mark.asyncio
async def test_zero_size_on_paper_rearms_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        PositionCalculatorDomainService,
        "calculate",
        staticmethod(lambda *a, **k: PositionCalculation(0.0, 0.0, 0.0, 0.0)),
    )
    engine = _engine(_Risk(True))
    strategy = await _armed(engine)

    await engine._process_signal(strategy, _signal(), BarCompletedEvent(close=100.0), _NOW, _NOW)

    assert strategy._open_direction is None


async def _with_fake_broker(broker: _FakeBroker) -> tuple[StrategyAppService, AsyncMock]:
    engine = _engine(_Risk(True))
    await engine.load_strategy(_config())
    engine._brokers["s1"] = broker  # type: ignore[assignment]
    strategy = engine._strategies["s1"]
    rejected = AsyncMock()
    strategy.on_order_rejected = rejected  # type: ignore[method-assign]
    await engine._process_signal(strategy, _signal(), BarCompletedEvent(close=100.0), _NOW, _NOW)
    return engine, rejected


@pytest.mark.asyncio
async def test_broker_rejection_reaches_strategy_once() -> None:
    broker = _FakeBroker(OrderStatus.REJECTED)

    _, rejected = await _with_fake_broker(broker)

    assert len(broker.submitted) == 1
    rejected.assert_awaited_once_with("venue says no")


@pytest.mark.asyncio
async def test_quantity_below_broker_minimum_skips_submit() -> None:
    broker = _FakeBroker(OrderStatus.FILLED, normalized=None)

    _, rejected = await _with_fake_broker(broker)

    assert broker.submitted == []
    rejected.assert_awaited_once_with("quantity below broker minimum")


@pytest.mark.asyncio
async def test_async_cancel_publishes_event_and_rejects_strategy() -> None:
    bus = EventBus()
    cancelled: list[OrderCancelledEvent] = []
    bus.subscribe(OrderCancelledEvent, lambda e: cancelled.append(e))
    orders = OrderAppService(bus, _InMemoryOrderRepo())  # type: ignore[arg-type]
    engine = _engine(_Risk(True), bus=bus, orders=orders)
    await engine.start()
    strategy = await _armed(engine)
    spy = AsyncMock(side_effect=strategy.on_order_rejected)
    strategy.on_order_rejected = spy  # type: ignore[method-assign]
    order = OrderAggregate.create(
        subscription_id="s1",
        symbol=_SYM,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=100.0,
    )
    broker = _FakeBroker(OrderStatus.SUBMITTED)
    await orders.submit(order, broker)  # type: ignore[arg-type]

    await orders.on_order_update(
        OrderResult(
            order_id=str(order.id),
            broker_order_id="",
            status=OrderStatus.CANCELLED,
            error_message="TRADING_RULE_INSUFFICIENT_MARGIN",
        )
    )

    assert len(cancelled) == 1
    assert cancelled[0].reason == "TRADING_RULE_INSUFFICIENT_MARGIN"
    spy.assert_awaited_once_with("TRADING_RULE_INSUFFICIENT_MARGIN")
    assert strategy._open_direction is None
