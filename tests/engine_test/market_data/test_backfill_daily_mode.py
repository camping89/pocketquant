from __future__ import annotations

from typing import cast

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.value_objects import (
    CALENDAR_CRYPTO_24_7,
    CALENDAR_EXNESS_FX,
)
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.engine.market_data.tracked_symbols_backfill import (
    BackfillTrackedSymbolCommand,
    TrackedSymbolBackfillService,
)

EURUSD = "EURUSD:EXNESS"


class _RecordingProvider:
    def __init__(self) -> None:
        self.requested: list[Interval] = []

    async def fetch_ohlcv(self, symbol: str, interval: Interval, n_bars: int = 1000) -> list[Bar]:
        self.requested.append(interval)
        return []

    async def search_symbols(self, query: str) -> list[dict]:
        return []

    async def close(self) -> None:
        return


class _StubCalendar:
    def __init__(self, calendar_id: str) -> None:
        self.calendar_id = calendar_id


class _StubCalendarFactory:
    def __init__(self, calendar_id: str) -> None:
        self._calendar = _StubCalendar(calendar_id)

    async def for_symbol(self, composite: str) -> _StubCalendar:  # noqa: ARG002
        return self._calendar


def _service(provider: _RecordingProvider, calendar_id: str) -> TrackedSymbolBackfillService:
    return TrackedSymbolBackfillService(
        provider=cast("object", provider),  # pyright: ignore[reportArgumentType]
        bar_repository=cast("object", None),  # pyright: ignore[reportArgumentType]
        calendar_factory=cast("TradingCalendarFactory", _StubCalendarFactory(calendar_id)),
    )


async def test_crypto_daily_backfill_still_cascades() -> None:
    provider = _RecordingProvider()
    result = await _service(provider, CALENDAR_CRYPTO_24_7).run(
        BackfillTrackedSymbolCommand(symbol="BTCUSDT:BINANCE", interval=Interval.DAY_1, n=10)
    )

    assert result["mode_used"] == "cascade"
    assert provider.requested == [Interval.MINUTE_1]


async def test_a_session_calendar_daily_auto_backfill_cascades() -> None:
    provider = _RecordingProvider()
    result = await _service(provider, CALENDAR_EXNESS_FX).run(
        BackfillTrackedSymbolCommand(symbol=EURUSD, interval=Interval.DAY_1, n=10)
    )

    assert result["mode_used"] == "cascade"
    assert provider.requested == [Interval.MINUTE_1]
