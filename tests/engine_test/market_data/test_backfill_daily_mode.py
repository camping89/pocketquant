"""A session-calendar daily backfill must go direct, never through the cascade.

A CME daily bar opens at 17:00 Chicago the evening before its own date, so
building one by aggregating 1m bars buckets it at UTC midnight and produces a bar
that never matches the vendor's chart. Crypto is unaffected, because its trading
day is the UTC day — which is exactly why no existing test can detect this.
"""

from __future__ import annotations

from typing import cast

import structlog.testing

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.value_objects import (
    CALENDAR_CME_GLOBEX_EQUITY,
    CALENDAR_CRYPTO_24_7,
)
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.engine.market_data.tracked_symbols_backfill import (
    BackfillTrackedSymbolCommand,
    TrackedSymbolBackfillService,
)


class _RecordingProvider:
    """Records which intervals were asked for; returns nothing."""

    def __init__(self) -> None:
        self.requested: list[Interval] = []

    async def fetch_ohlcv(
        self, symbol: str, interval: Interval, n_bars: int = 1000
    ) -> list[Bar]:
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


async def test_session_calendar_daily_backfill_goes_direct() -> None:
    provider = _RecordingProvider()
    result = await _service(provider, CALENDAR_CME_GLOBEX_EQUITY).run(
        BackfillTrackedSymbolCommand(symbol="ES1!:CME_MINI", interval=Interval.DAY_1, n=10)
    )

    assert result["mode_used"] == "direct"
    # The cascade path would have asked for 1m bars instead.
    assert provider.requested == [Interval.DAY_1]


async def test_crypto_daily_backfill_still_cascades() -> None:
    """The 24/7 path is unchanged — this is the G5 half of the override."""
    provider = _RecordingProvider()
    result = await _service(provider, CALENDAR_CRYPTO_24_7).run(
        BackfillTrackedSymbolCommand(symbol="BTCUSDT:BINANCE", interval=Interval.DAY_1, n=10)
    )

    assert result["mode_used"] == "cascade"
    assert provider.requested == [Interval.MINUTE_1]


async def test_an_explicit_cascade_is_overridden_audibly() -> None:
    """An explicit cascade is overridden, and says so.

    Honouring it would be the silent failure: ``cascade_tfs`` omits DAY_1 for a
    session calendar, so the request would persist 1m bars, build no daily bar,
    and still report success. Overriding without a word would be the other kind
    of silence, so the override is logged when it contradicts the caller.
    """
    provider = _RecordingProvider()
    with structlog.testing.capture_logs() as logs:
        result = await _service(provider, CALENDAR_CME_GLOBEX_EQUITY).run(
            BackfillTrackedSymbolCommand(
                symbol="ES1!:CME_MINI", interval=Interval.DAY_1, n=10, mode="cascade"
            )
        )

    assert result["mode_used"] == "direct"
    assert provider.requested == [Interval.DAY_1]
    overridden = [e for e in logs if e["event"] == "backfill.mode_overridden"]
    assert len(overridden) == 1
    assert overridden[0]["log_level"] == "warning"
    assert overridden[0]["requested_mode"] == "cascade"


async def test_auto_mode_is_overridden_silently() -> None:
    """Nothing was contradicted, so nothing is warned about."""
    provider = _RecordingProvider()
    with structlog.testing.capture_logs() as logs:
        await _service(provider, CALENDAR_CME_GLOBEX_EQUITY).run(
            BackfillTrackedSymbolCommand(symbol="ES1!:CME_MINI", interval=Interval.DAY_1, n=10)
        )

    assert [e for e in logs if e["event"] == "backfill.mode_overridden"] == []
