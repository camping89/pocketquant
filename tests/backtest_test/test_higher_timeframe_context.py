from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import structlog

from pocketquant.core.common.constants import COLLECTION_BARS, INTERVAL_SECONDS
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.strategy_service_interface import IStrategyService
from pocketquant.core.domain.strategy.value_objects import Signal, StrategyConfig
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.core.infra.calendars.exness_session_calendar_adapter import EXNESS_CALENDARS
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.backtest.backtest_sandbox_app_service import NoClosedTrades
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.execution.risk_check import RiskCheckHandler
from pocketquant.engine.strategy import strategy_app_service as engine_module
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

_BTC = "BTCUSDT:BINANCE"
_XAU = "XAUUSD:EXNESS"
_DAY = datetime(2026, 1, 5, tzinfo=UTC)
_MINUTE = timedelta(minutes=1)
_HOUR = timedelta(hours=1)
_AT_25 = timedelta(seconds=25)


class _CountingBars(BarRepository):
    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self.finds: Counter[str] = Counter()

    async def find(
        self, symbol: str, interval: Interval, start_date=None, end_date=None, limit: int = 5000
    ) -> list[Bar]:
        self.finds[interval.value] += 1
        return await super().find(symbol, interval, start_date, end_date, limit)


class _Calendars:
    def __init__(self, calendar: ITradingCalendarPort) -> None:
        self._calendar = calendar

    async def for_symbol(self, symbol: str) -> ITradingCalendarPort:
        return self._calendar


class _Recorder(IStrategyService):
    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self.seen: list[tuple] = []

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        context = {k: [(b.datetime, b.close) for b in v[-3:]] for k, v in bar["context"].items()}
        self.seen.append((bar["timestamp"], bar["close"], context))
        return None


class _Factory:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def create(self, broker_type: str, config: dict) -> PaperBrokerAdapter:
        return PaperBrokerAdapter(fill_delay_ms=0, event_bus=self._bus)


class _Repo:
    async def save(self, item) -> None:  # noqa: ANN001
        return None

    async def find_open(self, limit: int = 200) -> list:
        return []

    async def find_pending(self, limit: int = 500) -> list:
        return []


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(engine_module, "logger", structlog.get_logger("test.htf_context"))
    yield
    clear_simulation_time()


@pytest.fixture
async def bars(database: Database) -> _CountingBars:
    await database.get_collection(COLLECTION_BARS).drop()
    return _CountingBars(database)


def _engine(bars: BarRepository, calendar: ITradingCalendarPort) -> StrategyAppService:
    bus = EventBus()
    return StrategyAppService(
        event_bus=bus,
        broker_factory=_Factory(bus),  # type: ignore[arg-type]
        order_app_service=OrderAppService(bus, _Repo()),  # type: ignore[arg-type]
        position_app_service=PositionAppService(bus, _Repo()),  # type: ignore[arg-type]
        risk_check_handler=RiskCheckHandler(),
        bar_repository=bars,
        calendar_factory=_Calendars(calendar),  # type: ignore[arg-type]
        trade_repository=NoClosedTrades(),  # type: ignore[arg-type]
    )


async def _start(
    engine: StrategyAppService, sid: str, symbol: str, intervals: list[str], at: datetime
) -> _Recorder:
    set_simulation_time(at)
    if not engine.is_running:
        await engine.start()
    config = StrategyConfig(id=sid, name="t", symbol=symbol, intervals=intervals, broker="paper")
    await engine.load_strategy(config, _Recorder)
    await engine.start_strategy(sid)
    recorder = engine.get_strategy(sid)
    assert isinstance(recorder, _Recorder)
    return recorder


async def _seed(
    bars: BarRepository, symbol: str, interval: str, starts: list[datetime], closes: list[float]
) -> None:
    for start, close in zip(starts, closes, strict=True):
        bar = Bar(
            symbol=symbol,
            interval=Interval(interval),
            datetime=start,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1.0,
        )
        await bars.upsert_bar(bar, source="test")


async def _publish(
    engine: StrategyAppService, symbol: str, interval: str, start: datetime, close: float = 1.0
) -> None:
    bar_end = start + timedelta(seconds=INTERVAL_SECONDS[interval])
    set_simulation_time(bar_end + timedelta(seconds=1))
    await engine._event_bus.publish(
        BarCompletedEvent(
            symbol=symbol,
            interval=interval,
            bar_start=start,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1.0,
            tick_count=1,
            bar_end=bar_end,
            closed_at=bar_end,
            closed_by="timer",
        )
    )


def _minutes() -> list[datetime]:
    starts = [_DAY + i * _MINUTE for i in range(190)]
    gap = (_DAY + _HOUR + 30 * _MINUTE, _DAY + _HOUR + 50 * _MINUTE)
    return [s for s in starts if not gap[0] <= s < gap[1]]


def _minute_close(start: datetime) -> float:
    return float((start - _DAY) // _MINUTE)


async def _main_seed(bars: BarRepository) -> None:
    minutes = _minutes()
    await _seed(bars, _BTC, "1m", minutes, [_minute_close(m) for m in minutes])
    hours = [_DAY - 2 * _HOUR, _DAY - _HOUR, _DAY, _DAY + _HOUR, _DAY + 2 * _HOUR, _DAY + 3 * _HOUR]
    await _seed(bars, _BTC, "1h", hours, [98.0, 99.0, 100.0, 101.0, 102.0, 999.0])


def _context_at(recorder: _Recorder, start: datetime, interval: str) -> list[tuple]:
    return next(ctx[interval] for ts, _, ctx in recorder.seen if ts == start)


async def test_live_first_entry_bar_of_a_bucket_sees_the_previous_bucket_close(bars) -> None:
    await _main_seed(bars)
    engine = _engine(bars, Continuous24x7Calendar())
    recorder = await _start(engine, "a", _BTC, ["1m", "1h"], _DAY + 59 * _MINUTE + _AT_25)

    await _publish(engine, _BTC, "1m", _DAY + 59 * _MINUTE)
    await _publish(engine, _BTC, "1m", _DAY + _HOUR)

    assert _context_at(recorder, _DAY + _HOUR, "1h")[-1] == (_DAY, 100.0)


async def test_live_entry_bars_never_see_their_own_bucket(bars) -> None:
    await _main_seed(bars)
    engine = _engine(bars, Continuous24x7Calendar())
    recorder = await _start(engine, "a", _BTC, ["1m", "1h"], _DAY + 59 * _MINUTE + _AT_25)

    for start in (_DAY + 59 * _MINUTE, _DAY + _HOUR + 59 * _MINUTE, _DAY + 2 * _HOUR):
        await _publish(engine, _BTC, "1m", start)

    assert _context_at(recorder, _DAY + 59 * _MINUTE, "1h")[-1] == (_DAY - _HOUR, 99.0)
    assert _context_at(recorder, _DAY + _HOUR + 59 * _MINUTE, "1h")[-1] == (_DAY, 100.0)
    assert _context_at(recorder, _DAY + 2 * _HOUR, "1h")[-1] == (_DAY + _HOUR, 101.0)


async def test_a_partial_bucket_is_never_served(bars) -> None:
    await _main_seed(bars)
    engine = _engine(bars, Continuous24x7Calendar())
    recorder = await _start(engine, "a", _BTC, ["1m", "1h"], _DAY + 3 * _HOUR + _AT_25)

    live = [_DAY + 3 * _HOUR + i * _MINUTE for i in range(6)]
    for start in live:
        await _publish(engine, _BTC, "1m", start)

    for start in live:
        assert _context_at(recorder, start, "1h")[-1] == (_DAY + 2 * _HOUR, 102.0)
    assert all(close != 999.0 for _, _, ctx in recorder.seen for _, close in ctx["1h"])


async def test_context_is_read_once_per_rollover_for_two_instances(bars) -> None:
    await _main_seed(bars)
    engine = _engine(bars, Continuous24x7Calendar())
    at = _DAY + 58 * _MINUTE + _AT_25
    a = await _start(engine, "a", _BTC, ["1m", "1h"], at)
    b = await _start(engine, "b", _BTC, ["1m", "1h"], at)

    for minute in (58, 59, 60, 61):
        await _publish(engine, _BTC, "1m", _DAY + minute * _MINUTE)

    assert bars.finds["1h"] == 2
    assert _context_at(a, _DAY + _HOUR, "1h") == _context_at(b, _DAY + _HOUR, "1h")


async def test_exness_weekly_context_rolls_on_sunday(bars) -> None:
    weeks = [datetime(2026, 9, 27, tzinfo=UTC), datetime(2026, 10, 4, tzinfo=UTC)]
    weeks.append(datetime(2026, 10, 11, tzinfo=UTC))
    await _seed(bars, _XAU, "1w", weeks, [1.0, 2.0, 3.0])
    engine = _engine(bars, EXNESS_CALENDARS[1])
    at = datetime(2026, 10, 9, 20, 0, 25, tzinfo=UTC)
    recorder = await _start(engine, "a", _XAU, ["1h", "1w"], at)

    friday = datetime(2026, 10, 9, 19, tzinfo=UTC)
    sunday = datetime(2026, 10, 11, 22, tzinfo=UTC)
    await _publish(engine, _XAU, "1h", friday)
    await _publish(engine, _XAU, "1h", sunday)

    assert _context_at(recorder, friday, "1w")[-1] == (weeks[0], 1.0)
    assert _context_at(recorder, sunday, "1w")[-1] == (weeks[1], 2.0)


async def test_a_missing_previous_bucket_is_requeried_next_bar(bars) -> None:
    await _seed(bars, _BTC, "1h", [_DAY], [100.0])
    engine = _engine(bars, Continuous24x7Calendar())

    with structlog.testing.capture_logs() as logs:
        recorder = await _start(
            engine, "a", _BTC, ["1m", "1h"], _DAY + _HOUR + 59 * _MINUTE + _AT_25
        )
        await _publish(engine, _BTC, "1m", _DAY + 2 * _HOUR)
        await _publish(engine, _BTC, "1m", _DAY + 2 * _HOUR + _MINUTE)
        await _seed(bars, _BTC, "1h", [_DAY + _HOUR], [101.0])
        await _publish(engine, _BTC, "1m", _DAY + 2 * _HOUR + 2 * _MINUTE)
        await _publish(engine, _BTC, "1m", _DAY + 2 * _HOUR + 3 * _MINUTE)

    assert bars.finds["1h"] == 4
    assert _context_at(recorder, _DAY + 2 * _HOUR + 2 * _MINUTE, "1h")[-1] == (_DAY + _HOUR, 101.0)
    missing = [e for e in logs if e["event"] == "strategy.context_previous_bucket_missing"]
    assert len(missing) == 1


async def test_a_session_gap_bucket_is_cached(bars) -> None:
    tuesday = datetime(2026, 10, 13, tzinfo=UTC)
    hours = [tuesday + timedelta(hours=h) for h in (18, 19, 20)]
    await _seed(bars, _XAU, "1h", hours, [1.0, 2.0, 3.0])
    engine = _engine(bars, EXNESS_CALENDARS[1])

    with structlog.testing.capture_logs() as logs:
        at = tuesday + timedelta(hours=21, minutes=59) + _AT_25
        recorder = await _start(engine, "a", _XAU, ["15m", "1h"], at)
        await _publish(engine, _XAU, "15m", tuesday + timedelta(hours=22))
        await _publish(engine, _XAU, "15m", tuesday + timedelta(hours=22, minutes=15))

    assert bars.finds["1h"] == 2
    assert [ctx["1h"][-1] for _, _, ctx in recorder.seen] == [(hours[2], 3.0)] * 2
    assert [e for e in logs if e["log_level"] == "warning"] == []


async def test_warm_up_contexts_equal_live_contexts(bars) -> None:
    await _main_seed(bars)
    warm = await _start(
        _engine(bars, Continuous24x7Calendar()),
        "a",
        _BTC,
        ["1m", "1h"],
        _DAY + 3 * _HOUR + 10 * _MINUTE + _AT_25,
    )
    engine = _engine(bars, Continuous24x7Calendar())
    live = await _start(engine, "a", _BTC, ["1m", "1h"], _DAY + _AT_25)
    for start in _minutes():
        await _publish(engine, _BTC, "1m", start, _minute_close(start))

    assert len(warm.seen) == len(_minutes())
    assert warm.seen == live.seen


async def test_a_start_before_second_20_waits_and_replays_the_final_bar(
    bars, monkeypatch: pytest.MonkeyPatch
) -> None:
    noon = datetime(2026, 1, 5, 12, tzinfo=UTC)
    quarters = [noon - _HOUR + i * timedelta(minutes=15) for i in range(4)]
    await _seed(bars, _BTC, "15m", quarters, [1.0, 1.0, 1.0, 1.0])
    await _seed(bars, _BTC, "1h", [noon - 2 * _HOUR, noon - _HOUR], [1.0, 1.0])
    real = asyncio.sleep
    slept: list[float] = []

    async def fake(seconds: float, *args) -> None:  # noqa: ANN002
        if seconds < 1:
            await real(seconds, *args)
            return
        slept.append(seconds)
        await _seed(bars, _BTC, "15m", [quarters[-1]], [2.0])
        await _seed(bars, _BTC, "1h", [noon - _HOUR], [2.0])
        set_simulation_time(noon + timedelta(seconds=20))

    monkeypatch.setattr(engine_module.asyncio, "sleep", fake)
    engine = _engine(bars, Continuous24x7Calendar())
    recorder = await _start(engine, "a", _BTC, ["15m", "1h"], noon + timedelta(seconds=5))
    await _publish(engine, _BTC, "15m", noon)

    assert slept == [15.0]
    assert [close for ts, close, _ in recorder.seen if ts == quarters[-1]] == [2.0]
    assert _context_at(recorder, noon, "1h")[-1] == (noon - _HOUR, 2.0)
    assert bars.finds["1h"] == 1
