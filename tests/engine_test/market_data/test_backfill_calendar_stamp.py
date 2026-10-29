"""A backfilled bar carries the same calendar stamp as a synced one.

The scheduled sync stamps ``calendar_id`` and ``session_date`` before insert. The
backfill wrote provider bars as they came, so seeded CFD history had neither.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.value_objects import CALENDAR_EXNESS_XAUUSD
from pocketquant.core.infra.calendars.exness_session_calendar_adapter import (
    EXNESS_CALENDARS,
    ExnessSessionCalendarAdapter,
)
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.engine.market_data.tracked_symbols_backfill import (
    BackfillTrackedSymbolCommand,
    TrackedSymbolBackfillService,
)

XAUUSD = "XAUUSD:EXNESS"
SESSION_OPEN = datetime(2026, 10, 13, 0, 0, tzinfo=UTC)


class _OneBarProvider:
    async def fetch_ohlcv(self, symbol: str, interval: Interval, n_bars: int = 1000) -> list[Bar]:
        return [
            Bar(
                symbol=symbol,
                interval=interval,
                datetime=SESSION_OPEN,
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1.0,
            )
        ]


class _RecordingBarRepo:
    def __init__(self) -> None:
        self.upserted: list[Bar] = []

    async def upsert_bar(self, bar: Bar, source: str) -> None:  # noqa: ARG002
        self.upserted.append(bar)


class _XauusdFactory:
    async def for_symbol(self, composite: str) -> ExnessSessionCalendarAdapter:  # noqa: ARG002
        return EXNESS_CALENDARS[1]


async def test_direct_backfill_stamps_the_session_calendar() -> None:
    repo = _RecordingBarRepo()
    service = TrackedSymbolBackfillService(
        provider=cast("object", _OneBarProvider()),  # pyright: ignore[reportArgumentType]
        bar_repository=cast("object", repo),  # pyright: ignore[reportArgumentType]
        calendar_factory=cast("TradingCalendarFactory", _XauusdFactory()),
    )

    await service.run(BackfillTrackedSymbolCommand(symbol=XAUUSD, interval=Interval.DAY_1, n=1))

    [bar] = repo.upserted
    assert bar.calendar_id == CALENDAR_EXNESS_XAUUSD
    # An Exness daily bar opens at 00:00 UTC and its session day is the UTC date.
    assert bar.session_date == date(2026, 10, 13)
