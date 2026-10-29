"""A paper position never outlives its subscription or the process.

Unload drops the subscription's paper position, in the broker and in the
mirror, and disconnects a broker no other subscription holds. A restart deletes
the mirror rows of paper subscriptions and keeps every other row.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType
from pocketquant.core.domain.position import PositionAggregate, PositionSide
from pocketquant.core.domain.strategy import Direction, Signal
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


class _Factory:
    def __init__(self, bus: EventBus) -> None:
        self.created: list[PaperBrokerAdapter] = []
        self._bus = bus

    def create(self, broker_type: str, config: dict) -> PaperBrokerAdapter:
        broker = PaperBrokerAdapter(fill_delay_ms=0, event_bus=self._bus)
        self.created.append(broker)
        return broker


class _Repo:
    def __init__(self, rows: list[PositionAggregate] | None = None) -> None:
        self.rows = {str(p.id): p for p in rows or []}

    async def save(self, item) -> None:  # noqa: ANN001
        if isinstance(item, PositionAggregate):
            self.rows[str(item.id)] = item

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        return [p for p in self.rows.values() if not p.is_closed]

    async def find_pending(self, limit: int = 500) -> list:
        return []

    async def delete_open_by_subscription(self, subscription_id: str) -> int:
        gone = [k for k, p in self.rows.items() if p.subscription_id == subscription_id]
        for key in gone:
            del self.rows[key]
        return len(gone)


async def _engine() -> tuple[StrategyAppService, _Factory, PositionAppService, OrderAppService]:
    bus = EventBus()
    factory = _Factory(bus)
    mirror = PositionAppService(bus, _Repo())  # type: ignore[arg-type]
    orders = OrderAppService(bus, _Repo())  # type: ignore[arg-type]
    engine = StrategyAppService(
        event_bus=bus,
        broker_factory=factory,  # type: ignore[arg-type]
        order_app_service=orders,
        position_app_service=mirror,
        risk_check_handler=RiskCheckHandler(),
        bar_repository=NoStoredBars(),  # type: ignore[arg-type]
        calendar_factory=Continuous24x7CalendarFactory(),  # type: ignore[arg-type]
        trade_repository=NoClosedTrades(),  # type: ignore[arg-type]
    )
    await mirror.start()
    await engine.start()
    return engine, factory, mirror, orders


def _config(sid: str) -> StrategyConfig:
    return StrategyConfig(id=sid, name="t", symbol=_SYM, interval="1m", broker="paper")


async def _open(
    broker: PaperBrokerAdapter, sid: str, orders: OrderAppService | None = None
) -> None:
    order = OrderAggregate.create(
        subscription_id=sid,
        symbol=_SYM,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=100.0,
        sl_price=90.0,
    )
    if orders is None:
        await broker.submit_order(order)
    else:
        await orders.submit(order, broker)


@pytest.mark.asyncio
async def test_unload_drops_the_position_and_disconnects_a_broker_no_one_holds() -> None:
    engine, factory, mirror, orders = await _engine()
    await engine.load_strategy(_config("a"))
    broker = factory.created[0]
    await broker.connect()
    await _open(broker, "a", orders)
    assert mirror.get("a") is not None

    await engine.unload_strategy("a")

    assert await broker.get_positions() == []
    assert broker.is_connected is False
    assert mirror.get("a") is None


@pytest.mark.asyncio
async def test_unload_keeps_a_shared_broker_and_the_other_position() -> None:
    engine, factory, mirror, orders = await _engine()
    await engine.load_strategy(_config("a"))
    await engine.load_strategy(_config("b"))
    broker = factory.created[0]
    await broker.connect()
    await _open(broker, "a", orders)
    await _open(broker, "b", orders)

    await engine.unload_strategy("a")

    assert [p.subscription_id for p in await broker.get_positions()] == ["b"]
    assert broker.is_connected is True
    assert mirror.get("b") is not None


@pytest.mark.asyncio
async def test_boot_deletes_paper_rows_and_keeps_the_rest() -> None:
    def row(sid: str) -> PositionAggregate:
        return PositionAggregate.open(
            subscription_id=sid, symbol=_SYM, side=PositionSide.LONG, entry_price=1.0, quantity=1.0
        )

    repo = _Repo([row("paper-sub"), row("venue-sub")])
    mirror = PositionAppService(EventBus(), repo)  # type: ignore[arg-type]

    await mirror.start(frozenset({"paper-sub"}))

    assert [p.subscription_id for p in repo.rows.values()] == ["venue-sub"]
    assert mirror.get("paper-sub") is None
    assert mirror.get("venue-sub") is not None


@pytest.mark.asyncio
async def test_an_exit_queued_before_unload_does_not_open_a_new_position() -> None:
    bus = EventBus()
    broker = PaperBrokerAdapter(fill_delay_ms=0, event_bus=bus)
    await broker.connect()
    await _open(broker, "a")
    [pos] = await broker.get_positions()
    broker.drop_positions("a")

    await broker._fire_synthetic_exit(pos, 90.0, OrderSide.SELL, "stop_loss")

    assert await broker.get_positions() == []


@pytest.mark.asyncio
async def test_an_opposite_signal_keeps_the_paper_position() -> None:
    engine, factory, mirror, orders = await _engine()
    await engine.load_strategy(_config("a"))
    broker = factory.created[0]
    await broker.connect()
    await _open(broker, "a", orders)
    strategy = engine.get_strategy("a")
    assert strategy is not None
    short = Signal(
        symbol=_SYM,
        direction=Direction.SHORT,
        confidence=1.0,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        subscription_id="a",
    )

    await engine._process_signal(strategy, short, 100.0)

    assert [p.side for p in await broker.get_positions()] == [PositionSide.LONG]
    held = mirror.get("a")
    assert held is not None
    assert held.side == PositionSide.LONG
