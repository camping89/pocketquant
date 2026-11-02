from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import structlog

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.brokers.events import REASON_AUTO_SL
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderFilledEvent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from pocketquant.core.domain.position import PositionAggregate, TradeClosedEvent
from pocketquant.core.domain.strategy import Direction
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.infra.brokers.paper import paper_broker_adapter as paper_module
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.backtest.backtest_sandbox_app_service import NoClosedTrades
from pocketquant.engine.execution import order_app_service as orders_module
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.execution.risk_check import RiskCheckHandler
from pocketquant.engine.strategy import strategy_app_service as engine_module
from pocketquant.engine.strategy.strategy_app_service import _STALE_AFTER_S, StrategyAppService
from tests.strategy_doubles import (
    Continuous24x7CalendarFactory,
    NoStoredBars,
    ScriptedStrategy,
)

_SYM = "BTCUSDT:BINANCE"
_SID = "s1"
_T0 = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _sim_time(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # A module logger cached by an earlier test ignores capture_logs; rebind fresh ones.
    for module in (engine_module, orders_module, paper_module):
        monkeypatch.setattr(module, "logger", structlog.get_logger(module.__name__))
    set_simulation_time(_T0)
    yield
    clear_simulation_time()


class _Factory:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def create(self, broker_type: str, config: dict) -> PaperBrokerAdapter:
        return PaperBrokerAdapter(slippage_percent=0.0, fill_delay_ms=0, event_bus=self._bus)


class _Store:
    def __init__(self) -> None:
        self.rows: dict[str, object] = {}

    async def save(self, item: OrderAggregate | PositionAggregate) -> None:
        # A copy, so a test reads what was saved, not the live object.
        self.rows[str(item.id)] = item.model_copy(deep=True)

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        return []

    async def find_pending(self, limit: int = 500) -> list[OrderAggregate]:
        return []

    async def delete_open_by_subscription(self, subscription_id: str) -> int:
        return 0

    def orders(self) -> list[OrderAggregate]:
        return [o for o in self.rows.values() if isinstance(o, OrderAggregate)]


class _Paper:
    def __init__(self) -> None:
        self.bus = EventBus()
        self.order_store = _Store()
        self.orders = OrderAppService(self.bus, self.order_store)  # type: ignore[arg-type]
        self.mirror = PositionAppService(self.bus, _Store())  # type: ignore[arg-type]
        self.engine = StrategyAppService(
            event_bus=self.bus,
            broker_factory=_Factory(self.bus),  # type: ignore[arg-type]
            order_app_service=self.orders,
            position_app_service=self.mirror,
            risk_check_handler=RiskCheckHandler(),
            bar_repository=NoStoredBars(),  # type: ignore[arg-type]
            calendar_factory=Continuous24x7CalendarFactory(),  # type: ignore[arg-type]
            trade_repository=NoClosedTrades(),  # type: ignore[arg-type]
        )
        self.fills: list[OrderFilledEvent] = []
        self.trades: list[TradeClosedEvent] = []
        self.bus.subscribe(OrderFilledEvent, self.fills.append)
        self.bus.subscribe(TradeClosedEvent, self.trades.append)
        self.minute = 0

    @property
    def broker(self) -> PaperBrokerAdapter:
        broker = self.engine._brokers[_SID]
        assert isinstance(broker, PaperBrokerAdapter)
        return broker

    @property
    def strategy(self) -> ScriptedStrategy:
        strategy = self.engine.get_strategy(_SID)
        assert isinstance(strategy, ScriptedStrategy)
        return strategy

    def side_fills(self, side: OrderSide) -> list[OrderFilledEvent]:
        return [f for f in self.fills if f.side is side]

    # One closed 1m bar per call, published one second after its end unless late_s says
    # otherwise; simulation time moves with it, as the live clock would.
    async def bar(
        self,
        *,
        o: float = 100.0,
        h: float = 100.5,
        low: float = 99.5,
        c: float = 100.0,
        gap: bool = False,
        late_s: float = 1.0,
    ) -> None:
        start = _T0 + timedelta(minutes=self.minute)
        self.minute += 1
        end = start + timedelta(minutes=1)
        at = end + timedelta(seconds=late_s)
        set_simulation_time(at)
        await self.bus.publish(
            BarCompletedEvent(
                symbol=_SYM,
                interval="1m",
                bar_start=start,
                open=o,
                high=h,
                low=low,
                close=c,
                volume=1.0,
                tick_count=1,
                bar_end=end,
                gap=gap,
                closed_at=end,
                occurred_at=at,
            )
        )


async def _paper(*script: dict | None) -> _Paper:
    p = _Paper()
    await p.mirror.start()
    await p.engine.start()
    config = StrategyConfig(id=_SID, name="t", symbol=_SYM, intervals=["1m"], broker="paper")
    await p.engine.load_strategy(config, ScriptedStrategy)
    await p.engine.start_strategy(_SID)
    p.strategy.script = list(script)
    return p


def _stop(price: float, **overrides: object) -> dict:
    return {
        "entry_type": "stop",
        "entry_price": price,
        "stop_loss_price": price - 5.0,
        "take_profit_price": price + 20.0,
    } | overrides


_EXIT = {"direction": Direction.EXIT}
_MARKET = {"stop_loss_price": 50.0, "take_profit_price": 200.0}


# A position and its own pending stop co-exist only out of band (a venue fill not yet
# reported, a stored stop before takeover); the risk check refuses the signal path, so the
# test places the stop directly.
async def _open_with_a_pending_stop(p: _Paper) -> None:
    await p.bar()
    stop = OrderAggregate.create(
        subscription_id=_SID,
        symbol=_SYM,
        side=OrderSide.BUY,
        order_type=OrderType.STOP_MARKET,
        quantity=1.0,
        stop_price=200.0,
        sl_price=195.0,
    )
    await p.orders.submit(stop, p.broker)
    assert p.orders.pending_stop(_SID) is not None
    assert p.mirror.get(_SID) is not None


async def test_a_stop_replaced_every_bar_still_fills_on_the_bar_that_touches_it() -> None:
    p = await _paper(_stop(101.0), _stop(105.0))

    await p.bar()
    await p.bar(h=101.5, c=101.0)

    [buy] = p.side_fills(OrderSide.BUY)
    assert buy.filled_price == pytest.approx(101.0)
    assert p.mirror.get(_SID) is not None


async def test_a_new_signal_cancels_the_resting_stop_then_places() -> None:
    p = await _paper(_stop(105.0), _stop(104.0))

    await p.bar()
    await p.bar(h=102.0)

    first, second = p.order_store.orders()
    assert first.status is OrderStatus.CANCELLED
    assert second.status is OrderStatus.SUBMITTED
    pending = p.orders.pending_stop(_SID)
    assert pending is not None
    assert pending.id == second.id


async def test_an_unchanged_stop_is_kept() -> None:
    p = await _paper(_stop(105.0), _stop(105.0))
    await p.bar()
    submit = AsyncMock(wraps=p.broker.submit_order)
    p.broker.submit_order = submit  # type: ignore[method-assign]

    with structlog.testing.capture_logs() as logs:
        await p.bar(h=102.0)

    [order] = p.order_store.orders()
    assert order.status is OrderStatus.SUBMITTED
    submit.assert_not_called()
    assert [e["log_level"] for e in logs if e["event"] == "strategy.stop_kept"] == ["debug"]
    assert [e["event"] for e in logs if e["log_level"] == "info"] == []


async def test_exit_cancels_the_pending_stop_and_closes_the_position() -> None:
    p = await _paper(_MARKET, _EXIT)
    await _open_with_a_pending_stop(p)

    await p.bar()

    assert len(p.side_fills(OrderSide.SELL)) == 1
    assert len(p.trades) == 1
    assert p.orders.pending_stop(_SID) is None
    assert p.broker._resting == {}
    assert await p.broker.get_positions() == []
    assert p.mirror.get(_SID) is None


async def test_exit_closes_even_when_the_cancel_fails() -> None:
    p = await _paper(_MARKET, _EXIT)
    await _open_with_a_pending_stop(p)
    p.broker.cancel_order = AsyncMock(return_value=False)  # type: ignore[method-assign]

    with structlog.testing.capture_logs() as logs:
        await p.bar()

    assert len(p.side_fills(OrderSide.SELL)) == 1
    assert len([e for e in logs if e["event"] == "strategy.pending_cancel_failed"]) == 1
    assert await p.broker.get_positions() == []
    assert len(p.broker._resting) == 1


async def test_an_exit_on_a_gapped_bar_still_closes() -> None:
    p = await _paper(_MARKET, _EXIT, _MARKET)
    await p.bar()

    await p.bar(gap=True)
    await p.bar(gap=True)

    assert len(p.side_fills(OrderSide.SELL)) == 1
    assert len(p.side_fills(OrderSide.BUY)) == 1


async def test_an_exit_on_a_stale_bar_still_closes() -> None:
    p = await _paper(_MARKET, _EXIT, _MARKET)
    late = _STALE_AFTER_S["1m"] + 5.0
    await p.bar()

    await p.bar(late_s=late)
    await p.bar(late_s=late)

    assert len(p.side_fills(OrderSide.SELL)) == 1
    assert len(p.side_fills(OrderSide.BUY)) == 1


async def test_an_exit_bar_takes_the_sl_first() -> None:
    p = await _paper({"stop_loss_price": 99.0, "take_profit_price": 200.0}, _EXIT)
    await p.bar()

    with structlog.testing.capture_logs() as logs:
        await p.bar(o=100.0, h=100.0, low=98.0, c=98.5)

    [sell] = p.side_fills(OrderSide.SELL)
    assert sell.filled_price == pytest.approx(99.0)
    assert p.broker.get_order_events(sell.order_id)[-1].reason == REASON_AUTO_SL
    assert [e["log_level"] for e in logs if e["event"] == "strategy.exit_ignored"] == ["debug"]


async def test_exit_with_nothing_open_is_ignored() -> None:
    p = await _paper(_EXIT)

    with structlog.testing.capture_logs() as logs:
        await p.bar()

    assert p.order_store.orders() == []
    assert [e["log_level"] for e in logs if e["event"] == "strategy.exit_ignored"] == ["debug"]


async def test_stopping_a_subscription_cancels_its_pending_stop() -> None:
    p = await _paper(_stop(105.0))
    await p.bar()

    await p.engine.stop_strategy(_SID)

    [order] = p.order_store.orders()
    assert order.status is OrderStatus.CANCELLED
    assert p.broker._resting == {}


async def test_unloading_a_stopped_subscription_cancels_its_pending_stop() -> None:
    p = await _paper(_stop(105.0))
    await p.bar()
    broker = p.broker
    await p.strategy.on_stop()

    await p.engine.unload_strategy(_SID)

    [order] = p.order_store.orders()
    assert order.status is OrderStatus.CANCELLED
    assert p.orders.pending_stop(_SID) is None
    assert broker._resting == {}


async def test_a_handover_stop_cancels_the_pending_stop() -> None:
    p = await _paper(_stop(105.0))
    await p.bar()

    await p.engine.stop(timeout_s=0)

    [order] = p.order_store.orders()
    assert order.status is OrderStatus.CANCELLED
    assert p.orders.pending_stop(_SID) is None


async def test_no_stop_fills_without_the_lease() -> None:
    p = await _paper(_stop(101.0))
    await p.bar()
    p.engine.trading_until = None

    await p.bar(h=102.0)

    assert p.side_fills(OrderSide.BUY) == []
    [order] = p.order_store.orders()
    assert order.status is OrderStatus.SUBMITTED
    assert order.order_type is OrderType.STOP_MARKET


async def test_a_stop_with_new_exits_is_replaced() -> None:
    p = await _paper(_stop(105.0), _stop(105.0, stop_loss_price=101.0))

    await p.bar()
    await p.bar(h=102.0)

    first, second = p.order_store.orders()
    assert first.status is OrderStatus.CANCELLED
    assert (second.status, second.sl_price) == (OrderStatus.SUBMITTED, 101.0)


async def test_a_stop_entry_is_rejected_while_a_position_is_open() -> None:
    p = await _paper(_MARKET, _stop(200.0, stop_loss_price=150.0))
    await p.bar()

    with structlog.testing.capture_logs() as logs:
        await p.bar()

    assert p.orders.pending_stop(_SID) is None
    assert [e["reason"] for e in logs if e["event"] == "signal_rejected_by_risk"] == [
        "position open"
    ]


# The bar handler is mid-submit (the paper fill delay) when the reconcile loop acts.
async def _act_during_submit(p: _Paper, action) -> None:  # noqa: ANN001
    submit = p.broker.submit_order

    async def slow_submit(order: OrderAggregate, **kwargs: object) -> object:
        result = await submit(order, **kwargs)  # type: ignore[arg-type]
        await action()
        return result

    p.broker.submit_order = slow_submit  # type: ignore[method-assign]
    await p.bar()


async def test_a_stop_placed_while_its_strategy_stops_is_cancelled() -> None:
    p = await _paper(_stop(105.0))
    broker = p.broker

    await _act_during_submit(p, lambda: p.engine.stop_strategy(_SID))

    [order] = p.order_store.orders()
    assert order.status is OrderStatus.CANCELLED
    assert broker._resting == {}


async def test_a_reload_after_an_unload_mid_submit_still_trades() -> None:
    p = await _paper(_stop(105.0))
    await _act_during_submit(p, lambda: p.engine.unload_strategy(_SID))
    config = StrategyConfig(id=_SID, name="t", symbol=_SYM, intervals=["1m"], broker="paper")
    await p.engine.load_strategy(config, ScriptedStrategy)
    await p.engine.start_strategy(_SID)
    p.strategy.script = [_stop(106.0)]

    with structlog.testing.capture_logs() as logs:
        await p.bar()

    assert [o.status for o in p.order_store.orders()] == [
        OrderStatus.CANCELLED,
        OrderStatus.SUBMITTED,
    ]
    assert [e for e in logs if e["event"] == "strategy.pending_cancel_failed"] == []
