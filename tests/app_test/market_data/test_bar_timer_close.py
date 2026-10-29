"""BarAppService close path: publish outside the bar lock, timer close, the closed boundary."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.shared.enums import Interval
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
