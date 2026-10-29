"""A started strategy is warmed up from stored bars and gets its direction from the mirror."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import structlog

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import OrderFilledEvent, OrderSide
from pocketquant.core.domain.position import PositionAggregate, PositionSide
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy import Direction, Signal
from pocketquant.core.domain.strategy.services.hitnrun2_strategy_service import (
    HitNRun2StrategyService,
)
from pocketquant.core.domain.strategy.strategy_service_interface import IStrategyService
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.backtest.backtest_sandbox_app_service import (
    Continuous24x7CalendarFactory,
    NoClosedTrades,
)
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.execution.risk_check import RiskCheckHandler
from pocketquant.engine.strategy import strategy_app_service as engine_module
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

_SYM = "XAUUSD:EXNESS"
# Bucket T opens at 12:00; the clock is at second 25 of it, so the start never waits.
_T = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
_NOW = _T + timedelta(seconds=25)
_MINUTE = timedelta(minutes=1)


class _StoredBars:
    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    async def find(
        self, symbol: str, interval: Interval, start_date=None, end_date=None, limit: int = 5000
    ) -> list[Bar]:
        found = [b for b in self._bars if end_date is None or b.datetime <= end_date]
        return sorted(found, key=lambda b: b.datetime, reverse=True)[:limit]


class _Factory:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def create(self, broker_type: str, config: dict) -> PaperBrokerAdapter:
        return PaperBrokerAdapter(fill_delay_ms=0, event_bus=self._bus)


class _Repo:
    def __init__(self, rows: list[PositionAggregate] | None = None) -> None:
        self.rows = rows or []

    async def save(self, item) -> None:  # noqa: ANN001
        return None

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        return list(self.rows)

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


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(engine_module, "logger", structlog.get_logger("test.warm_up"))
    set_simulation_time(_NOW)
    yield
    clear_simulation_time()


def _flat(count: int, last_start: datetime) -> list[Bar]:
    return [
        Bar(
            symbol=_SYM,
            interval=Interval.MINUTE_1,
            datetime=last_start - i * _MINUTE,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1.0,
        )
        for i in range(count)
    ]


async def _engine(
    bars: list[Bar],
    strategy_class: type[IStrategyService],
    rows: list[PositionAggregate] | None = None,
) -> tuple[StrategyAppService, EventBus, list[OrderFilledEvent]]:
    bus = EventBus()
    mirror = PositionAppService(bus, _Repo(rows))  # type: ignore[arg-type]
    await mirror.load_open_positions()
    engine = StrategyAppService(
        event_bus=bus,
        broker_factory=_Factory(bus),  # type: ignore[arg-type]
        order_app_service=OrderAppService(bus, _Repo()),  # type: ignore[arg-type]
        position_app_service=mirror,
        risk_check_handler=RiskCheckHandler(),
        bar_repository=_StoredBars(bars),  # type: ignore[arg-type]
        calendar_factory=Continuous24x7CalendarFactory(),  # type: ignore[arg-type]
        trade_repository=NoClosedTrades(),  # type: ignore[arg-type]
    )
    fills: list[OrderFilledEvent] = []
    bus.subscribe(OrderFilledEvent, fills.append)
    await engine.start()
    config = StrategyConfig(id="a", name="t", symbol=_SYM, interval="1m", broker="paper")
    await engine.load_strategy(config, strategy_class)
    await engine.start_strategy("a")
    return engine, bus, fills


def _live(start: datetime, close: float) -> BarCompletedEvent:
    return BarCompletedEvent(
        symbol=_SYM,
        interval="1m",
        bar_start=start,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
        tick_count=1,
        bar_end=start + _MINUTE,
        closed_at=start + _MINUTE,
        closed_by="timer",
    )


async def test_hitnrun2_signals_on_the_first_live_bar_after_481_stored_bars() -> None:
    engine, bus, fills = await _engine(_flat(481, _T - _MINUTE), HitNRun2StrategyService)
    strategy = engine.get_strategy("a")
    assert isinstance(strategy, HitNRun2StrategyService)
    assert len(strategy._closes) == 481
    assert fills == []

    set_simulation_time(_T + _MINUTE + timedelta(seconds=1))
    await bus.publish(_live(_T, close=90.0))

    assert [f.side for f in fills if f.side == OrderSide.BUY] == [OrderSide.BUY]


async def test_a_replayed_signal_sends_nothing() -> None:
    bars = _flat(481, _T - 2 * _MINUTE)
    breakdown = _flat(1, _T - _MINUTE)[0].model_copy(update={"low": 89.0, "close": 90.0})
    engine, _, fills = await _engine([*bars, breakdown], HitNRun2StrategyService)

    strategy = engine.get_strategy("a")
    assert isinstance(strategy, HitNRun2StrategyService)
    assert fills == []
    assert strategy._open_direction is None


async def test_a_long_mirror_row_restores_direction_long() -> None:
    row = PositionAggregate.open(
        subscription_id="a", symbol=_SYM, side=PositionSide.LONG, entry_price=1.0, quantity=1.0
    )
    engine, _, _ = await _engine(_flat(10, _T - _MINUTE), HitNRun2StrategyService, [row])

    strategy = engine.get_strategy("a")
    assert isinstance(strategy, HitNRun2StrategyService)
    assert strategy._open_direction == Direction.LONG


async def test_a_hole_after_the_stored_bars_warns_once_and_gap_skips() -> None:
    with structlog.testing.capture_logs() as logs:
        engine, bus, fills = await _engine(_flat(10, _T - 5 * _MINUTE), _AlwaysLong)
    assert len([e for e in logs if e["event"] == "strategy.warmup_incomplete"]) == 1

    set_simulation_time(_T + _MINUTE + timedelta(seconds=1))
    with structlog.testing.capture_logs() as logs:
        await bus.publish(_live(_T, close=100.0))

    skipped = [e for e in logs if e["event"] == "strategy.entry_skipped"]
    assert [e["reason"] for e in skipped] == ["gap"]
    assert fills == []
