"""Venue entries run as tasks outside the bar handler, one per subscription; paper stays inline."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import structlog

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.brokers.broker_port import IBrokerPort, OrderCallback, TradeCallback
from pocketquant.core.domain.brokers.value_objects import AccountBalance, OrderResult
from pocketquant.core.domain.order import OrderAggregate, OrderStatus
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

_SYM = "XAUUSD:EXNESS"
_T = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


class _VenueBroker(IBrokerPort):
    """An async-fill broker whose submit takes ``submit_s``; ``hold`` blocks sizing."""

    fills_async = True

    def __init__(self, submit_s: float = 1.0, hold: asyncio.Event | None = None) -> None:
        self.submit_s = submit_s
        self.hold = hold
        self.starts: list[tuple[str, float]] = []

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

    async def normalize_quantity(self, symbol: str, quantity: float) -> float | None:
        if self.hold is not None:
            await self.hold.wait()
        return quantity

    async def submit_order(
        self, order: OrderAggregate, *, deadline: datetime | None = None
    ) -> OrderResult:
        self.starts.append((order.subscription_id, time.monotonic()))
        await asyncio.sleep(self.submit_s)
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
        return AccountBalance(total_equity=10_000.0, available_balance=10_000.0)

    async def subscribe_order_updates(self, callback: OrderCallback) -> None:
        return None

    async def unsubscribe_order_updates(self) -> None:
        return None

    async def subscribe_trades(self, callback: TradeCallback) -> None:
        return None

    async def unsubscribe_trades(self) -> None:
        return None


class _Factory:
    """One broker per broker type; ``paper`` builds a real paper broker."""

    def __init__(self, bus: EventBus, brokers: dict[str, IBrokerPort] | None = None) -> None:
        self._bus = bus
        self.brokers = brokers or {}

    def create(self, broker_type: str, config: dict) -> IBrokerPort:
        if broker_type == "paper":
            self.brokers["paper"] = PaperBrokerAdapter(fill_delay_ms=0, event_bus=self._bus)
        return self.brokers[broker_type]


class _Repo:
    async def save(self, item) -> None:  # noqa: ANN001
        return None

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        return []

    async def find_pending(self, limit: int = 500) -> list:
        return []


class _AlwaysLong(IStrategyService):
    gate: asyncio.Event | None = None

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        if self.gate is not None:
            await self.gate.wait()
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
    monkeypatch.setattr(engine_module, "logger", structlog.get_logger("test.concurrent_opens"))
    set_simulation_time(_T + timedelta(seconds=61))
    yield
    clear_simulation_time()


async def _engine(
    subs: dict[str, str], brokers: dict[str, IBrokerPort] | None = None
) -> StrategyAppService:
    """``subs`` maps subscription id to broker type."""
    bus = EventBus()
    engine = StrategyAppService(
        event_bus=bus,
        broker_factory=_Factory(bus, brokers),  # type: ignore[arg-type]
        order_app_service=OrderAppService(bus, _Repo()),  # type: ignore[arg-type]
        position_app_service=PositionAppService(bus, _Repo()),  # type: ignore[arg-type]
        risk_check_handler=RiskCheckHandler(),
        bar_repository=NoStoredBars(),  # type: ignore[arg-type]
        calendar_factory=Continuous24x7CalendarFactory(),  # type: ignore[arg-type]
        trade_repository=NoClosedTrades(),  # type: ignore[arg-type]
    )
    await engine.start()
    for sid, broker_type in subs.items():
        config = StrategyConfig(id=sid, name="t", symbol=_SYM, interval="1m", broker=broker_type)
        await engine.load_strategy(config, _AlwaysLong)
        await engine.start_strategy(sid)
    return engine


async def _handle(engine: StrategyAppService, event: BarCompletedEvent) -> None:
    # Bounded: an inline signal blocked at the broker would hang the test.
    await asyncio.wait_for(engine._on_bar_completed(event), 2.0)


def _bar(start: datetime = _T) -> BarCompletedEvent:
    return BarCompletedEvent(
        symbol=_SYM,
        interval="1m",
        bar_start=start,
        open=100.0,
        high=100.0,
        low=100.0,
        close=100.0,
        volume=1.0,
        tick_count=1,
        bar_end=start + timedelta(minutes=1),
        closed_at=start + timedelta(minutes=1),
        closed_by="timer",
    )


async def test_three_venue_signals_submit_concurrently() -> None:
    venue = _VenueBroker()
    engine = await _engine({"a": "venue", "b": "venue", "c": "venue"}, {"venue": venue})

    began = time.monotonic()
    await _handle(engine, _bar())
    assert time.monotonic() - began < 0.1

    await asyncio.sleep(0.05)
    starts = [t for _, t in venue.starts]
    assert len(starts) == 3
    assert max(starts) - min(starts) < 0.1
    await asyncio.gather(*engine._signal_tasks.values())


async def test_a_second_signal_while_the_task_runs_is_skipped() -> None:
    venue = _VenueBroker()
    engine = await _engine({"a": "venue"}, {"venue": venue})
    await _handle(engine, _bar())
    await asyncio.sleep(0.01)
    later = _T + timedelta(minutes=1)
    set_simulation_time(later + timedelta(seconds=61))

    with structlog.testing.capture_logs() as logs:
        await _handle(engine, _bar(later))

    skipped = [e for e in logs if e["event"] == "strategy.entry_skipped"]
    assert [e["reason"] for e in skipped] == ["inflight"]
    await asyncio.gather(*engine._signal_tasks.values())
    assert [sid for sid, _ in venue.starts] == ["a"]


async def test_paper_stays_inline() -> None:
    engine = await _engine({"a": "paper"})

    await _handle(engine, _bar())

    broker = engine._brokers["a"]
    assert len(await broker.get_positions()) == 1
    assert engine._signal_tasks == {}


async def test_a_running_bar_handler_is_counted() -> None:
    engine = await _engine({"a": "paper"})
    gate = asyncio.Event()
    strategy = engine.get_strategy("a")
    assert isinstance(strategy, _AlwaysLong)
    strategy.gate = gate

    task = asyncio.create_task(engine._on_bar_completed(_bar()))
    await asyncio.sleep(0.01)
    assert engine._running_bar_handlers == 1

    gate.set()
    await task
    assert engine._running_bar_handlers == 0


async def test_cancel_pending_signals_spares_a_task_at_the_broker() -> None:
    blocked = _VenueBroker(hold=asyncio.Event())
    sending = _VenueBroker(submit_s=0.2)
    engine = await _engine(
        {"a": "blocked", "b": "sending"}, {"blocked": blocked, "sending": sending}
    )
    await _handle(engine, _bar())
    await asyncio.sleep(0.05)
    task_a = engine._signal_tasks["a"]
    task_b = engine._signal_tasks["b"]

    with structlog.testing.capture_logs() as logs:
        assert engine.cancel_pending_signals() == 1
        await asyncio.gather(task_a, task_b, return_exceptions=True)

    assert task_a.cancelled()
    assert not task_b.cancelled()
    assert [sid for sid, _ in sending.starts] == ["b"]
    [discarded] = [e for e in logs if e["event"] == "strategy.signal_discarded"]
    assert discarded["reason"] == "lease"
    assert discarded["subscription_id"] == "a"
    assert discarded["log_level"] == "info"


async def test_stop_waits_at_most_the_timeout() -> None:
    engine = await _engine({"a": "venue"}, {"venue": _VenueBroker(submit_s=5.0)})
    await _handle(engine, _bar())
    await asyncio.sleep(0.01)
    task = engine._signal_tasks["a"]

    began = time.monotonic()
    with structlog.testing.capture_logs() as logs:
        await engine.stop(timeout_s=0.2)
    assert time.monotonic() - began < 0.5
    await asyncio.sleep(0)
    assert task.cancelled()
    [timeout] = [e for e in logs if e["event"] == "strategy_engine.stop_timeout"]
    assert timeout["pending"] == 1

    engine = await _engine({"a": "venue"}, {"venue": _VenueBroker(submit_s=0.1)})
    await _handle(engine, _bar())
    task = engine._signal_tasks["a"]
    with structlog.testing.capture_logs() as logs:
        await engine.stop(timeout_s=1.0)
    assert task.done() and not task.cancelled()
    assert [e for e in logs if e["event"] == "strategy_engine.stop_timeout"] == []
