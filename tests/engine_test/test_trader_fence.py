"""A standby engine connects no broker; the in-flight count the trader drains on."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.domain.strategy import Direction, Signal
from pocketquant.core.domain.strategy.strategy_service_interface import IStrategyService
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.backtest.backtest_sandbox_app_service import (
    Continuous24x7CalendarFactory,
    NoClosedTrades,
    NoStoredBars,
)
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.execution.risk_check import RiskCheckHandler
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

_SYM = "BTCUSDT:BINANCE"


class _CountingBroker(PaperBrokerAdapter):
    """A paper broker that counts connects and reports a settable in-flight count."""

    connects = 0
    inflight = 0

    async def connect(self) -> None:
        self.connects += 1
        await super().connect()

    @property
    def inflight_count(self) -> int:
        return self.inflight


class _Factory:
    def __init__(self, bus: EventBus) -> None:
        self.created: list[_CountingBroker] = []
        self._bus = bus

    def create(self, broker_type: str, config: dict) -> PaperBrokerAdapter:
        broker = _CountingBroker(fill_delay_ms=0, event_bus=self._bus)
        self.created.append(broker)
        return broker


class _Repo:
    async def save(self, item) -> None:  # noqa: ANN001
        return None

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        return []

    async def find_pending(self, limit: int = 500) -> list:
        return []


class _AlwaysLong(IStrategyService):
    async def on_bar_completed(self, bar: dict) -> Signal | None:
        return Signal(
            symbol=bar["symbol"],
            direction=Direction.LONG,
            confidence=1.0,
            timestamp=bar["timestamp"],
            subscription_id=self.id,
            stop_loss_price=bar["close"] * 0.95,
        )


async def _standby_engine() -> tuple[StrategyAppService, _CountingBroker]:
    bus = EventBus()
    factory = _Factory(bus)
    engine = StrategyAppService(
        event_bus=bus,
        broker_factory=factory,  # type: ignore[arg-type]
        order_app_service=OrderAppService(bus, _Repo()),  # type: ignore[arg-type]
        position_app_service=PositionAppService(bus, _Repo()),  # type: ignore[arg-type]
        risk_check_handler=RiskCheckHandler(),
        bar_repository=NoStoredBars(),  # type: ignore[arg-type]
        calendar_factory=Continuous24x7CalendarFactory(),  # type: ignore[arg-type]
        trade_repository=NoClosedTrades(),  # type: ignore[arg-type]
    )
    await engine.start()
    engine.trading_until = None
    config = StrategyConfig(id="a", name="t", symbol=_SYM, interval="1m", broker="paper")
    await engine.load_strategy(config, _AlwaysLong)
    await engine.start_strategy("a")
    return engine, factory.created[0]


async def test_standby_engine_connects_no_broker_on_start() -> None:
    engine, broker = await _standby_engine()
    assert broker.connects == 0

    engine.trading_until = datetime.now(UTC) + timedelta(seconds=25)
    await engine.take_over()

    assert broker.connects == 1
    await engine.stop(timeout_s=1.0)


async def test_inflight_count_counts_signal_tasks_bar_handlers_and_broker_orders() -> None:
    engine, broker = await _standby_engine()

    async def open_in_flight() -> None:
        await asyncio.Event().wait()

    signal_task = asyncio.create_task(open_in_flight())
    engine._signal_tasks["a"] = signal_task
    engine._running_bar_handlers = 1
    broker.inflight = 2

    assert engine.inflight_count() == 4

    signal_task.cancel()
    await asyncio.gather(signal_task, return_exceptions=True)
    engine._running_bar_handlers = 0
    broker.inflight = 0
    assert engine.inflight_count() == 0
