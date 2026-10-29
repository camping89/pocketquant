"""BarAppService close path: publish outside the bar lock, timer close, the closed boundary."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pocketquant.core.common.constants import CACHE_KEY_BAR_CURRENT
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


def _at(hour: int, minute: int, second: float = 0.0, *, day: int = 13) -> datetime:
    whole = int(second)
    return datetime(2026, 10, day, hour, minute, whole, round((second - whole) * 1e6), tzinfo=UTC)


def _tick(symbol: str, ts: datetime, price: float = 1.0) -> QuoteTick:
    return QuoteTick(symbol=symbol, timestamp=ts, price=price, volume=1.0)


def _service(
    intervals: list[Interval] | None = None, calendar_factory: object | None = None
) -> tuple[BarAppService, EventBus, AsyncMock]:
    cache = AsyncMock(spec=Cache)
    cache.get = AsyncMock(return_value=None)
    bus = EventBus()
    svc = BarAppService(
        cache=cache,
        bar_repository=AsyncMock(spec=BarRepository),
        event_bus=bus,
        intervals=intervals or [Interval.MINUTE_1],
        calendar_factory=calendar_factory,  # type: ignore[arg-type]
    )
    return svc, bus, cache


async def test_a_slow_bar_handler_does_not_block_another_symbol() -> None:
    svc, bus, _ = _service()

    async def slow(event: BarCompletedEvent) -> None:
        if event.symbol == "AAA:EXNESS":
            await asyncio.sleep(0.3)

    bus.subscribe(BarCompletedEvent, slow)

    async def feed_aaa() -> None:
        await svc.add_tick(_tick("AAA:EXNESS", _at(12, 0, 10)))
        await svc.add_tick(_tick("AAA:EXNESS", _at(12, 1, 1)))

    task = asyncio.create_task(feed_aaa())
    await asyncio.sleep(0.01)

    began = time.monotonic()
    await svc.add_tick(_tick("BBB:EXNESS", _at(12, 1, 2)))

    assert time.monotonic() - began < 0.1
    assert not task.done()
    await task


# -- timer close --------------------------------------------------------------


class _FxCalendars:
    """Stands in for TradingCalendarFactory: every symbol is on the Exness FX calendar."""

    async def for_symbol(self, symbol: str) -> ITradingCalendarPort:
        return next(c for c in EXNESS_CALENDARS if c.calendar_id == CALENDAR_EXNESS_FX)


def _collect(bus: EventBus) -> list[BarCompletedEvent]:
    events: list[BarCompletedEvent] = []
    bus.subscribe(BarCompletedEvent, events.append)
    return events


def _blocking(bus: EventBus) -> asyncio.Event:
    release = asyncio.Event()

    async def wait(event: BarCompletedEvent) -> None:
        if event.symbol == "AAA:EXNESS":
            await release.wait()

    bus.subscribe(BarCompletedEvent, wait)
    return release


async def _close_at(svc: BarAppService, now: datetime) -> None:
    set_simulation_time(now)
    await svc.close_due_bars()


@pytest.fixture(autouse=True)
def _clear_clock() -> Iterator[None]:
    yield
    clear_simulation_time()


async def test_a_1m_bar_closes_on_the_timer_half_a_second_after_its_end() -> None:
    svc, bus, _ = _service()
    events = _collect(bus)
    await svc.add_tick(_tick("AAA:EXNESS", _at(12, 0, 30)))

    await _close_at(svc, _at(12, 1, 0.4))
    assert events == []

    await _close_at(svc, _at(12, 1, 0.6))
    [event] = events
    assert event.closed_by == "timer"
    assert event.bar_end == _at(12, 1)
    assert event.closing_tick_at is None
    assert event.closed_at == _at(12, 1, 0.6)


async def test_a_late_tick_for_a_timer_closed_bucket_is_dropped() -> None:
    svc, bus, _ = _service()
    events = _collect(bus)
    await svc.add_tick(_tick("AAA:EXNESS", _at(12, 0, 30)))
    await _close_at(svc, _at(12, 1, 0.6))
    assert len(events) == 1

    await svc.add_tick(_tick("AAA:EXNESS", _at(12, 0, 59.9)))
    assert len(events) == 1
    assert Interval.MINUTE_1 not in svc._bars["AAA:EXNESS"]

    await svc.add_tick(_tick("AAA:EXNESS", _at(12, 1, 5)))
    assert len(events) == 1
    assert svc._bars["AAA:EXNESS"][Interval.MINUTE_1].bar_start == _at(12, 1)


async def test_a_tick_close_before_the_timer_is_not_published_twice() -> None:
    svc, bus, _ = _service()
    events = _collect(bus)
    await svc.add_tick(_tick("AAA:EXNESS", _at(12, 0, 30)))
    await svc.add_tick(_tick("AAA:EXNESS", _at(12, 1, 0.2)))
    assert [e.closed_by for e in events] == ["tick"]

    await _close_at(svc, _at(12, 1, 0.6))

    assert len(events) == 1


async def test_a_4h_bar_closes_on_the_timer_at_its_bucket_end() -> None:
    svc, bus, _ = _service([Interval.HOUR_4], _FxCalendars())
    events = _collect(bus)
    await svc.add_tick(_tick("EURUSD:EXNESS", _at(20, 10, day=16)))

    await _close_at(svc, _at(0, 0, 0.4, day=17))
    assert events == []

    await _close_at(svc, _at(0, 0, 0.6, day=17))
    [event] = events
    assert event.closed_by == "timer"
    assert event.bar_end == _at(0, 0, day=17)


async def test_last_closed_boundary_moves_after_the_publish_returns() -> None:
    svc, bus, _ = _service()
    release = _blocking(bus)
    await svc.add_tick(_tick("AAA:EXNESS", _at(12, 0, 30)))
    set_simulation_time(_at(12, 1, 0.6))
    task = asyncio.create_task(svc.close_due_bars())

    await asyncio.sleep(0.01)
    assert svc.last_closed_boundary is None

    release.set()
    await task
    assert svc.last_closed_boundary == _at(12, 1)


async def test_a_failing_handler_does_not_drop_other_symbols() -> None:
    svc, bus, _ = _service()

    def fail(event: BarCompletedEvent) -> None:
        if event.symbol == "AAA:EXNESS":
            raise RuntimeError("handler failed")

    bus.subscribe(BarCompletedEvent, fail)
    events = _collect(bus)
    await svc.add_tick(_tick("AAA:EXNESS", _at(12, 0, 30)))
    await svc.add_tick(_tick("BBB:EXNESS", _at(12, 0, 31)))

    await _close_at(svc, _at(12, 1, 0.6))

    assert [e.symbol for e in events] == ["AAA:EXNESS", "BBB:EXNESS"]
    assert svc.last_closed_boundary == _at(12, 1)


async def test_a_running_tick_close_publish_holds_the_boundary() -> None:
    svc, bus, _ = _service()
    release = _blocking(bus)

    async def feed() -> None:
        await svc.add_tick(_tick("AAA:EXNESS", _at(12, 0, 30)))
        await svc.add_tick(_tick("AAA:EXNESS", _at(12, 1, 0.2)))

    task = asyncio.create_task(feed())
    await asyncio.sleep(0.01)

    await _close_at(svc, _at(12, 1, 0.6))
    assert svc.last_closed_boundary is None

    release.set()
    await task
    await svc.close_due_bars()
    assert svc.last_closed_boundary == _at(12, 1)


async def test_an_idle_service_still_advances_the_boundary() -> None:
    svc, _, _ = _service()

    await _close_at(svc, _at(12, 5, 0.6))

    assert svc.last_closed_boundary == _at(12, 5)


async def test_bar_current_is_written_only_while_publishing() -> None:
    svc, _, cache = _service()
    svc.publishes_current = False
    await svc.add_tick(_tick("AAA:EXNESS", _at(12, 0, 10)))
    await svc.add_tick(_tick("AAA:EXNESS", _at(12, 1, 1)))
    cache.set.assert_not_awaited()
    cache.delete.assert_not_awaited()

    svc.publishes_current = True
    await svc.add_tick(_tick("AAA:EXNESS", _at(12, 1, 2)))

    cache.set.assert_awaited_once()
    key, value = cache.set.await_args.args
    assert key == CACHE_KEY_BAR_CURRENT.format(symbol="AAA:EXNESS", interval="1m")
    assert value["gap"] is False
    assert value["coverage_start"] == _at(12, 1).isoformat()


async def test_a_bar_cut_by_the_session_close_ends_at_the_close() -> None:
    svc, bus, _ = _service([Interval.HOUR_1], _FxCalendars())
    events = _collect(bus)
    await svc.add_tick(_tick("EURUSD:EXNESS", _at(20, 58, 30, day=16)))
    assert svc._bars["EURUSD:EXNESS"][Interval.HOUR_1].bar_end == _at(20, 59, day=16)

    await _close_at(svc, _at(20, 59, 0.6, day=16))

    [event] = events
    assert event.bar_end == _at(20, 59, day=16)
