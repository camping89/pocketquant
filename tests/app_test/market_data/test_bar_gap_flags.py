"""BarAppService gap facts: tick silence, a stale or missing restart seed, the weekend."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.value_objects import CALENDAR_EXNESS_FX
from pocketquant.core.infra.calendars.exness_session_calendar_adapter import EXNESS_CALENDARS
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.market_data.app_services.bar_app_service import BarAppService
from pocketquant.engine.market_data.app_services.quote_dto import QuoteTick

SYMBOL = "EURUSD:EXNESS"


class _FxCalendars:
    """Stands in for TradingCalendarFactory: every symbol is on the Exness FX calendar."""

    async def for_symbol(self, symbol: str) -> ITradingCalendarPort:
        return next(c for c in EXNESS_CALENDARS if c.calendar_id == CALENDAR_EXNESS_FX)


def _at(hour: int, minute: int, second: int = 0, *, day: int = 13) -> datetime:
    return datetime(2026, 10, day, hour, minute, second, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clear_clock() -> Iterator[None]:
    yield
    clear_simulation_time()


async def _run(
    ticks: list[datetime],
    *,
    seed: dict[str, Any] | None = None,
    interval: Interval = Interval.MINUTE_5,
    price: float = 1.25,
) -> tuple[BarAppService, list[BarCompletedEvent]]:
    """Feed ``ticks`` and close the first bar on the timer; return the service and events."""
    cache = AsyncMock(spec=Cache)
    cache.get = AsyncMock(return_value=seed)
    bus = EventBus()
    events: list[BarCompletedEvent] = []
    bus.subscribe(BarCompletedEvent, events.append)
    svc = BarAppService(
        cache=cache,
        bar_repository=AsyncMock(spec=BarRepository),
        event_bus=bus,
        intervals=[interval],
        calendar_factory=_FxCalendars(),  # type: ignore[arg-type]
    )
    for ts in ticks:
        await svc.add_tick(QuoteTick(symbol=SYMBOL, timestamp=ts, price=price, volume=1.0))
    if interval == Interval.MINUTE_5:
        end = svc._bars[SYMBOL][interval].bar_end
        assert end is not None
        set_simulation_time(end + timedelta(seconds=0.6))
        await svc.close_due_bars()
    return svc, events


def _seed(**fields: Any) -> dict[str, Any]:
    seed: dict[str, Any] = {
        "bar_start": "2026-10-13T10:05:00+00:00",
        "open": 1.1,
        "high": 1.3,
        "low": 1.0,
        "close": 1.2,
        "volume": 5.0,
        "tick_count": 7,
        "gap": False,
        "coverage_start": "2026-10-13T10:05:00+00:00",
        "last_update": _at(10, 7).timestamp(),
    }
    seed.update(fields)
    return {k: v for k, v in seed.items() if v is not None}


async def test_a_61_second_silence_sets_gap() -> None:
    times = [_at(10, 0, 5), _at(10, 1, 6), _at(10, 1, 56), _at(10, 2, 46)]
    _, events = await _run([*times, _at(10, 3, 36), _at(10, 4, 26)])

    assert events[0].gap is True


async def test_a_59_second_silence_does_not() -> None:
    times = [_at(10, 0, 5), _at(10, 1, 4), _at(10, 1, 54), _at(10, 2, 44)]
    _, events = await _run([*times, _at(10, 3, 34), _at(10, 4, 24)])

    assert events[0].gap is False


async def test_a_tail_silence_over_60_seconds_sets_gap() -> None:
    times = [_at(10, 0, 5), _at(10, 0, 55), _at(10, 1, 45), _at(10, 2, 35)]
    _, events = await _run([*times, _at(10, 3, 25), _at(10, 3, 58)])

    assert events[0].gap is True


async def test_a_mid_bucket_start_without_seed_sets_gap() -> None:
    times = [_at(10, 1, 10), _at(10, 2), _at(10, 2, 50), _at(10, 3, 40), _at(10, 4, 30)]
    _, events = await _run(times)

    assert events[0].gap is True


async def test_an_early_start_without_seed_has_no_gap() -> None:
    times = [_at(10, 0, 40), _at(10, 1, 30), _at(10, 2, 20), _at(10, 3, 10)]
    _, events = await _run([*times, _at(10, 4), _at(10, 4, 50)])

    assert events[0].gap is False


SEEDED_TICKS = [_at(10, 7, 30), _at(10, 8, 20), _at(10, 9, 10)]


async def test_a_fresh_seed_covers_the_start() -> None:
    _, events = await _run(SEEDED_TICKS, seed=_seed())

    [bar] = events
    assert (bar.open, bar.high, bar.low, bar.close) == (1.1, 1.3, 1.0, 1.25)
    assert bar.tick_count == 10
    assert bar.gap is False


async def test_an_old_seed_sets_gap() -> None:
    _, events = await _run(SEEDED_TICKS, seed=_seed(last_update=_at(10, 5, 50).timestamp()))

    [bar] = events
    assert bar.gap is True
    assert bar.open == 1.25


async def test_a_gapped_seed_keeps_its_gap() -> None:
    seed = _seed(gap=True, coverage_start="2026-10-13T10:06:30+00:00")
    _, events = await _run(SEEDED_TICKS, seed=seed)

    [bar] = events
    assert bar.gap is True
    assert bar.open == 1.1


async def test_a_seed_without_coverage_start_is_not_used() -> None:
    _, events = await _run(SEEDED_TICKS, seed=_seed(gap=None, coverage_start=None))

    [bar] = events
    assert bar.open == 1.25
    assert bar.gap is True


async def test_a_weekend_silence_is_not_a_gap() -> None:
    friday = [_at(20, 0, 10, day=16) + timedelta(seconds=50 * i) for i in range(71)]
    assert friday[-1] == _at(20, 58, 30, day=16)
    svc, events = await _run([*friday, _at(21, 5, 10, day=18)], interval=Interval.HOUR_4)

    [bar] = events
    assert bar.bar_start == _at(20, 0, day=16)
    assert bar.gap is False
    assert svc._bars[SYMBOL][Interval.HOUR_4].gap is False
