"""A restarted trading process rebuilds each paper broker's cash and positions at takeover."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import structlog

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderFilledEvent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from pocketquant.core.domain.position import PositionAggregate, PositionSide
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.trading import Trade
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.backtest.backtest_sandbox_app_service import (
    Continuous24x7CalendarFactory,
    NoStoredBars,
)
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.execution.risk_check import RiskCheckHandler
from pocketquant.engine.live.live_trade_collector import LiveTradeCollector
from pocketquant.engine.strategy import strategy_app_service as engine_module
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

_SYM = "BTCUSDT:BINANCE"


class _Positions:
    def __init__(self) -> None:
        self.rows: dict[str, PositionAggregate] = {}

    async def save(self, position: PositionAggregate) -> None:
        self.rows[str(position.id)] = position.model_copy(deep=True)

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        return [p.model_copy(deep=True) for p in self.rows.values() if not p.is_closed]

    async def delete_open_by_subscription(self, subscription_id: str) -> int:
        gone = [
            k
            for k, p in self.rows.items()
            if p.subscription_id == subscription_id and not p.is_closed
        ]
        for key in gone:
            del self.rows[key]
        return len(gone)


class _Orders:
    def __init__(self) -> None:
        self.rows: dict[str, OrderAggregate] = {}

    async def save(self, order: OrderAggregate) -> None:
        self.rows[str(order.id)] = order

    async def find_pending(self, limit: int = 500) -> list[OrderAggregate]:
        return [o for o in self.rows.values() if o.status == OrderStatus.PENDING]


class _Trades:
    def __init__(self) -> None:
        self.trades: list[Trade] = []

    async def save_many(self, trades: list[Trade]) -> None:
        self.trades.extend(trades)

    async def realized_net(self, run_ids: list[str]) -> float:
        return sum(t.pnl - t.commission for t in self.trades if t.run_id in run_ids)


@dataclass
class _Store:
    positions: _Positions = field(default_factory=_Positions)
    orders: _Orders = field(default_factory=_Orders)
    trades: _Trades = field(default_factory=_Trades)


@dataclass
class _Process:
    engine: StrategyAppService
    bus: EventBus
    orders: OrderAppService
    fills: list[OrderFilledEvent]

    @property
    def broker(self) -> PaperBrokerAdapter:
        broker = self.engine._brokers["a"]
        assert isinstance(broker, PaperBrokerAdapter)
        return broker


@pytest.fixture(autouse=True)
def _fresh_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(engine_module, "logger", structlog.get_logger("test.paper_restore"))


async def _process(store: _Store) -> _Process:
    """One app process on the shared store: mirror, orders, engine and trade collector."""
    bus = EventBus()
    mirror = PositionAppService(bus, store.positions)  # type: ignore[arg-type]
    await mirror.start()
    orders = OrderAppService(bus, store.orders)  # type: ignore[arg-type]
    engine = StrategyAppService(
        event_bus=bus,
        broker_factory=BrokerFactory(bus, safeguards_repository=AsyncMock()),
        order_app_service=orders,
        position_app_service=mirror,
        risk_check_handler=RiskCheckHandler(),
        default_broker_config={"initial_balance": 10_000.0, "commission_bps": 10},
        bar_repository=NoStoredBars(),  # type: ignore[arg-type]
        calendar_factory=Continuous24x7CalendarFactory(),  # type: ignore[arg-type]
        trade_repository=store.trades,  # type: ignore[arg-type]
    )
    await engine.start()
    await LiveTradeCollector(bus, store.trades, engine).start()  # type: ignore[arg-type]
    fills: list[OrderFilledEvent] = []
    bus.subscribe(OrderFilledEvent, fills.append)
    config = StrategyConfig(id="a", name="t", symbol=_SYM, interval="1m", broker="paper")
    await engine.load_strategy(config)
    await engine.start_strategy("a")
    return _Process(engine, bus, orders, fills)


async def _open(process: _Process, price: float, sl: float) -> None:
    order = OrderAggregate.create(
        subscription_id="a",
        symbol=_SYM,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=price,
        sl_price=sl,
    )
    await process.orders.submit(order, process.broker)


def _bar(low: float, close: float = 100.0) -> BarCompletedEvent:
    start = datetime.now(UTC).replace(second=0, microsecond=0)
    return BarCompletedEvent(
        symbol=_SYM,
        interval="1m",
        bar_start=start,
        open=close,
        high=close,
        low=low,
        close=close,
        volume=1.0,
        tick_count=1,
        occurred_at=datetime.now(UTC) + timedelta(seconds=1),
    )


async def _before_restart() -> tuple[_Store, float]:
    """Process A closes one round trip on its SL and keeps a second LONG open."""
    store = _Store()
    a = await _process(store)
    await _open(a, price=100.0, sl=95.0)
    await a.bus.publish(_bar(low=90.0))
    assert len(store.trades.trades) == 1
    await _open(a, price=100.0, sl=94.0)
    return store, (await a.broker.get_balance()).available_balance


async def test_a_rebuilt_paper_broker_shows_the_pre_restart_balance() -> None:
    store, before = await _before_restart()
    b = await _process(store)
    assert b.engine._discard_reason == "standby"

    await b.engine.take_over()

    assert (await b.broker.get_balance()).available_balance == pytest.approx(before)
    [held] = await b.broker.get_positions()
    assert held.sl_price == 94.0
    assert b.engine._discard_reason == "drain"


async def test_a_restored_position_exits_on_the_next_crossing_bar() -> None:
    store, _ = await _before_restart()
    b = await _process(store)
    await b.engine.take_over()

    await b.bus.publish(_bar(low=90.0))

    assert [f.side for f in b.fills] == [OrderSide.SELL]
    assert await b.broker.get_positions() == []


async def test_a_paper_row_without_exits_is_dropped() -> None:
    store = _Store()
    row = PositionAggregate.open(
        subscription_id="a", symbol=_SYM, side=PositionSide.LONG, entry_price=100.0, quantity=1.0
    )
    await store.positions.save(row)
    b = await _process(store)

    with structlog.testing.capture_logs() as logs:
        await b.engine.take_over()

    assert len([e for e in logs if e["event"] == "paper_position_dropped_no_exits"]) == 1
    assert await store.positions.find_open() == []
    assert await b.broker.get_positions() == []
