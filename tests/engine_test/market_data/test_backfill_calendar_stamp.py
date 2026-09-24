"""A backfilled bar carries the same calendar stamp as a synced one.

The scheduled sync stamps ``calendar_id`` and ``session_date`` before insert. The
backfill wrote provider bars as they came, so seeded futures history had neither.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.value_objects import CALENDAR_CME_GLOBEX_EQUITY
from pocketquant.core.infra.calendars.cme_globex_calendar_adapter import CmeGlobexCalendarAdapter
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.engine.market_data.tracked_symbols_backfill import (
    BackfillTrackedSymbolCommand,
    TrackedSymbolBackfillService,
)

ES = "ES1!:CME_MINI"
SESSION_OPEN = datetime(2026, 9, 22, 22, 0, tzinfo=UTC)


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


class _CmeFactory:
    async def for_symbol(self, composite: str) -> CmeGlobexCalendarAdapter:  # noqa: ARG002
        return CmeGlobexCalendarAdapter()


async def test_direct_backfill_stamps_the_session_calendar() -> None:
    repo = _RecordingBarRepo()
    service = TrackedSymbolBackfillService(
        provider=cast("object", _OneBarProvider()),  # pyright: ignore[reportArgumentType]
        bar_repository=cast("object", repo),  # pyright: ignore[reportArgumentType]
        calendar_factory=cast("TradingCalendarFactory", _CmeFactory()),
    )

    await service.run(BackfillTrackedSymbolCommand(symbol=ES, interval=Interval.DAY_1, n=1))

    [bar] = repo.upserted
    assert bar.calendar_id == CALENDAR_CME_GLOBEX_EQUITY
    # The session opening the evening of 09-22 is CME's trading day 09-23.
    assert bar.session_date == date(2026, 9, 23)
