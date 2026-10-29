"""Entry guards on live bars: stale, gapped, non-successor, seen, standby and lease.

Exits never depend on them: a paper SL still fills on a bar whose entry is skipped.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import structlog

from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType
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
from pocketquant.engine.strategy import strategy_app_service as engine_module
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

_SYM = "BTCUSDT:BINANCE"
_T = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


class _DeadlineBroker(PaperBrokerAdapter):
    """A paper broker that records the deadline each order carries."""

    deadlines: list[datetime | None]

    async def submit_order(self, order, *, deadline=None):  # noqa: ANN001, ANN201
        self.deadlines.append(deadline)
        return await super().submit_order(order, deadline=deadline)


class _Factory:
    def __init__(self, bus: EventBus) -> None:
        self.created: list[_DeadlineBroker] = []
        self._bus = bus

    def create(self, broker_type: str, config: dict) -> PaperBrokerAdapter:
        broker = _DeadlineBroker(fill_delay_ms=0, event_bus=self._bus)
        broker.deadlines = []
        self.created.append(broker)
        return broker


class _Repo:
    def __init__(self) -> None:
        self.rows: dict[str, object] = {}

    async def save(self, item) -> None:  # noqa: ANN001
        self.rows[str(item.id)] = item

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        return []

    async def find_pending(self, limit: int = 500) -> list:
        return []

    async def delete_open_by_subscription(self, subscription_id: str) -> int:
        return 0


class _AlwaysLong(IStrategyService):
    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self.bars = 0

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        self.bars += 1
        return Signal(
            symbol=bar["symbol"],
            direction=Direction.LONG,
            confidence=1.0,
            timestamp=bar["timestamp"],
            subscription_id=self.id,
            stop_loss_price=bar["close"] * 0.95,
        )


@pytest.fixture(autouse=True)
def _fresh_logger(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(engine_module, "logger", structlog.get_logger("test.strategy_engine"))
    yield
    clear_simulation_time()


async def _engine(
    interval: str = "1m",
) -> tuple[StrategyAppService, EventBus, _DeadlineBroker, OrderAppService]:
    bus = EventBus()
    factory = _Factory(bus)
    orders = OrderAppService(bus, _Repo())  # type: ignore[arg-type]
    engine = StrategyAppService(
        event_bus=bus,
        broker_factory=factory,  # type: ignore[arg-type]
        order_app_service=orders,
        position_app_service=PositionAppService(bus, _Repo()),  # type: ignore[arg-type]
        risk_check_handler=RiskCheckHandler(),
        bar_repository=NoStoredBars(),  # type: ignore[arg-type]
        calendar_factory=Continuous24x7CalendarFactory(),  # type: ignore[arg-type]
        trade_repository=NoClosedTrades(),  # type: ignore[arg-type]
    )
    await engine.start()
    config = StrategyConfig(id="a", name="t", symbol=_SYM, interval=interval, broker="paper")
    await engine.load_strategy(config, _AlwaysLong)
    await engine.start_strategy("a")
    return engine, bus, factory.created[0], orders


def _bar(
    start: datetime,
    interval: str = "1m",
    *,
    close: float = 100.0,
    low: float | None = None,
    gap: bool = False,
    live: bool = True,
) -> BarCompletedEvent:
    end = start + timedelta(seconds=INTERVAL_SECONDS[interval])
    return BarCompletedEvent(
        symbol=_SYM,
        interval=interval,
        bar_start=start,
        open=close,
        high=close,
        low=close if low is None else low,
        close=close,
        volume=1.0,
        tick_count=1,
        bar_end=end if live else None,
        gap=gap,
        closed_at=end if live else None,
        closed_by="timer",
    )


def _events(logs: list[Any], name: str) -> list[Any]:
    return [entry for entry in logs if entry["event"] == name]


async def _positions(broker: PaperBrokerAdapter, sid: str = "a") -> list:
    return [p for p in await broker.get_positions() if p.subscription_id == sid]


@pytest.mark.parametrize("offset", [0, 1])
@pytest.mark.parametrize(
    ("interval", "budget"),
    [("1m", 10), ("5m", 30), ("15m", 60), ("1h", 120), ("4h", 300), ("1d", 600), ("1w", 600)],
)
async def test_stale_budget(interval: str, budget: int, offset: int) -> None:
    _, bus, broker, _ = await _engine(interval)
    event = _bar(_T, interval)
    assert event.bar_end is not None
    set_simulation_time(event.bar_end + timedelta(seconds=budget + offset))

    with structlog.testing.capture_logs() as logs:
        await bus.publish(event)

    skipped = _events(logs, "strategy.entry_skipped")
    if offset == 0:
        assert len(await _positions(broker)) == 1
        assert skipped == []
    else:
        assert await _positions(broker) == []
        assert [e["reason"] for e in skipped] == ["stale"]


async def test_a_gap_flagged_bar_skips_the_entry() -> None:
    _, bus, broker, _ = await _engine()
    set_simulation_time(_T + timedelta(seconds=61))

    with structlog.testing.capture_logs() as logs:
        await bus.publish(_bar(_T, gap=True))

    assert [e["reason"] for e in _events(logs, "strategy.entry_skipped")] == ["gap"]
    assert await _positions(broker) == []


async def test_a_non_successor_bar_skips_the_entry() -> None:
    _, bus, _, _ = await _engine()
    set_simulation_time(_T + timedelta(seconds=61))
    await bus.publish(_bar(_T))
    later = _T + timedelta(minutes=2)
    set_simulation_time(later + timedelta(seconds=61))

    with structlog.testing.capture_logs() as logs:
        await bus.publish(_bar(later))

    assert [e["reason"] for e in _events(logs, "strategy.entry_skipped")] == ["gap"]


async def test_paper_sl_still_fills_on_a_stale_bar() -> None:
    engine, bus, broker, orders = await _engine()
    await engine.load_strategy(
        StrategyConfig(id="b", name="t", symbol=_SYM, interval="1m", broker="paper")
    )
    held = OrderAggregate.create(
        subscription_id="b",
        symbol=_SYM,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        price=100.0,
        sl_price=95.0,
    )
    await orders.submit(held, broker)
    assert len(await _positions(broker, "b")) == 1
    set_simulation_time(_T + timedelta(minutes=5))

    with structlog.testing.capture_logs() as logs:
        await bus.publish(_bar(_T, close=92.0, low=90.0))

    assert await _positions(broker, "b") == []
    assert await _positions(broker, "a") == []
    assert [e["reason"] for e in _events(logs, "strategy.entry_skipped")] == ["stale"]


async def test_a_backtest_event_never_skips() -> None:
    _, bus, broker, _ = await _engine()
    set_simulation_time(_T + timedelta(days=1))

    await bus.publish(_bar(_T, live=False))

    assert len(await _positions(broker)) == 1


async def test_a_seen_bar_is_ignored() -> None:
    engine, bus, _, _ = await _engine()
    set_simulation_time(_T + timedelta(seconds=61))
    event = _bar(_T)

    await bus.publish(event)
    await bus.publish(event)

    strategy = engine.get_strategy("a")
    assert isinstance(strategy, _AlwaysLong)
    assert strategy.bars == 1


async def test_standby_discards_the_signal() -> None:
    engine, bus, broker, _ = await _engine()
    engine.trading_until = None
    set_simulation_time(_T + timedelta(seconds=61))

    with structlog.testing.capture_logs() as logs:
        await bus.publish(_bar(_T))

    assert await _positions(broker) == []
    assert _events(logs, "strategy.entry_skipped") == []
    [discarded] = _events(logs, "strategy.signal_discarded")
    assert discarded["reason"] == "standby"
    assert discarded["log_level"] == "debug"


async def test_a_drained_engine_discards_at_info() -> None:
    engine, bus, broker, _ = await _engine()
    engine._discard_reason = "drain"
    engine.trading_until = None
    set_simulation_time(_T + timedelta(seconds=61))

    with structlog.testing.capture_logs() as logs:
        await bus.publish(_bar(_T))

    assert await _positions(broker) == []
    [discarded] = _events(logs, "strategy.signal_discarded")
    assert discarded["reason"] == "drain"
    assert discarded["log_level"] == "info"


async def test_the_order_deadline_is_trading_until() -> None:
    engine, bus, broker, _ = await _engine()
    bar_end = _T + timedelta(minutes=1)
    engine.trading_until = bar_end + timedelta(seconds=25)
    set_simulation_time(bar_end + timedelta(seconds=1))

    await bus.publish(_bar(_T))

    assert broker.deadlines == [bar_end + timedelta(seconds=25)]


async def test_an_expired_lease_skips_the_entry() -> None:
    engine, bus, broker, _ = await _engine()
    now = _T + timedelta(seconds=61)
    engine.trading_until = now
    set_simulation_time(now)

    with structlog.testing.capture_logs() as logs:
        await bus.publish(_bar(_T))

    assert [e["reason"] for e in _events(logs, "strategy.entry_skipped")] == ["lease"]
    assert await _positions(broker) == []


async def test_one_latency_line_per_live_signal() -> None:
    _, bus, _, _ = await _engine()
    set_simulation_time(_T + timedelta(seconds=61))

    with structlog.testing.capture_logs() as logs:
        await bus.publish(_bar(_T))

    [line] = _events(logs, "live.signal_latency")
    for key in (
        "t0_bar_end",
        "t1_closing_tick",
        "t2_closed",
        "t3_published",
        "t4_signal",
        "t5_submit",
        "t6_returned",
        "t0_t5_ms",
        "t0_t6_ms",
        "closed_by",
    ):
        assert key in line

    _, backtest_bus, _, _ = await _engine()
    with structlog.testing.capture_logs() as logs:
        await backtest_bus.publish(_bar(_T, live=False))
    assert _events(logs, "live.signal_latency") == []
