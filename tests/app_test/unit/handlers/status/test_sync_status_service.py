from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.time import to_utc_iso
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.sync_status.entities import SyncStatus
from pocketquant.engine.market_data.sync_status_service import (
    SyncStatusQueryService,
)

SYMBOL = "BINANCE:BTCUSDT"
# Whole seconds: BSON stores milliseconds and the JSON contract emits seconds,
# so a fixture with microseconds would assert a precision nothing can produce.
NOW = datetime.now(UTC).replace(microsecond=0)


def _status(interval: str, last_bar_age_seconds: int, bar_count: int = 1000) -> SyncStatus:
    return SyncStatus(
        symbol=SYMBOL,
        interval=interval,
        status="completed",
        bar_count=bar_count,
        last_sync_at=NOW - timedelta(seconds=last_bar_age_seconds),
        last_bar_at=NOW - timedelta(seconds=last_bar_age_seconds),
    )


def _bar(dt: datetime, interval: Interval) -> Bar:
    return Bar(
        symbol=SYMBOL,
        interval=interval,
        datetime=dt,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
        tick_count=1,
    )


@pytest.fixture
def sync_status_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def bar_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def calendar_factory() -> AsyncMock:
    factory = AsyncMock()
    factory.for_symbol = AsyncMock(return_value=Continuous24x7Calendar())
    return factory


# Without it, the one bar a test configures would also stand in for the symbol's 1m feed and
# make every row look delayed.
class _FreshFeedBarRepo:
    def __init__(self, inner: AsyncMock) -> None:
        self._inner = inner
        self.count = inner.count

    async def get_latest(self, symbol: str, interval: Interval):
        if interval is Interval.MINUTE_1:
            return _bar(NOW - timedelta(seconds=60), Interval.MINUTE_1)
        return await self._inner.get_latest(symbol, interval)


@pytest.fixture
def handler(sync_status_repo, bar_repo, calendar_factory) -> SyncStatusQueryService:
    return SyncStatusQueryService(sync_status_repo, _FreshFeedBarRepo(bar_repo), calendar_factory)


# get_sync_status — list of all tracked symbols/intervals


# sync_status.last_bar_at is 1h old (stuck at a 5m cadence), but bar_repo.get_latest is 1m
# old.
@pytest.mark.asyncio
async def test_cascade_fresh_bars_show_not_stuck(handler, sync_status_repo, bar_repo) -> None:
    sync_status_repo.find_all.return_value = [
        _status("5m", last_bar_age_seconds=3600, bar_count=100),
    ]
    bar_repo.get_latest.return_value = _bar(NOW - timedelta(seconds=60), Interval.MINUTE_5)
    bar_repo.count.return_value = 150

    result = await handler.get_sync_status()

    assert len(result) == 1
    assert result[0].is_stuck is False
    assert result[0].bar_count == 150  # ← from bars, not sync_status (100)


# Stuck means bar age above 3x the cadence.
@pytest.mark.asyncio
async def test_all_stuck_when_bars_old(handler, sync_status_repo, bar_repo) -> None:
    sync_status_repo.find_all.return_value = [_status("5m", last_bar_age_seconds=60)]
    bar_repo.get_latest.return_value = _bar(NOW - timedelta(seconds=2000), Interval.MINUTE_5)
    bar_repo.count.return_value = 10

    result = await handler.get_sync_status()

    # 5m cadence = 300s; 3× = 900s; bar age 2000s > 900s → stuck
    assert result[0].is_stuck is True


@pytest.mark.asyncio
async def test_no_bars_yet_returns_not_stuck(handler, sync_status_repo, bar_repo) -> None:
    sync_status_repo.find_all.return_value = [_status("5m", last_bar_age_seconds=60)]
    bar_repo.get_latest.return_value = None
    bar_repo.count.return_value = 0

    result = await handler.get_sync_status()

    assert result[0].is_stuck is False
    assert result[0].bar_count == 0
    assert result[0].last_bar_at is None


@pytest.mark.asyncio
async def test_count_overrides_status_count(handler, sync_status_repo, bar_repo) -> None:
    sync_status_repo.find_all.return_value = [_status("1h", last_bar_age_seconds=60, bar_count=999)]
    bar_repo.get_latest.return_value = _bar(NOW - timedelta(seconds=60), Interval.HOUR_1)
    bar_repo.count.return_value = 5907

    result = await handler.get_sync_status()

    assert result[0].bar_count == 5907


@pytest.mark.asyncio
async def test_per_row_exception_isolated_with_fallback(
    handler,
    sync_status_repo,
    bar_repo,
) -> None:
    sync_status_repo.find_all.return_value = [
        _status("5m", last_bar_age_seconds=60, bar_count=10),
        _status("15m", last_bar_age_seconds=60, bar_count=20),
    ]

    fresh_bar = _bar(NOW - timedelta(seconds=60), Interval.MINUTE_15)

    async def get_latest_side_effect(symbol, interval):
        if interval == Interval.MINUTE_5:
            raise RuntimeError("boom")
        return fresh_bar

    async def count_side_effect(symbol, interval):
        if interval == Interval.MINUTE_5:
            raise RuntimeError("boom")
        return 999

    bar_repo.get_latest.side_effect = get_latest_side_effect
    bar_repo.count.side_effect = count_side_effect

    result = await handler.get_sync_status()

    assert len(result) == 2
    # Row 0 (5m) failed → fell back to sync_status
    assert result[0].interval == "5m"
    assert result[0].bar_count == 10  # sync_status fallback
    # Row 1 (15m) succeeded
    assert result[1].interval == "15m"
    assert result[1].bar_count == 999


@pytest.mark.asyncio
async def test_empty_status_list_returns_empty(handler, sync_status_repo, bar_repo) -> None:
    sync_status_repo.find_all.return_value = []
    result = await handler.get_sync_status()
    assert result == []
    bar_repo.get_latest.assert_not_called()
    bar_repo.count.assert_not_called()


@pytest.mark.asyncio
async def test_last_sync_at_still_from_sync_status(handler, sync_status_repo, bar_repo) -> None:
    sync_dt = NOW - timedelta(hours=2)
    s = _status("5m", last_bar_age_seconds=60)
    s.last_sync_at = sync_dt
    sync_status_repo.find_all.return_value = [s]
    bar_repo.get_latest.return_value = _bar(NOW - timedelta(seconds=60), Interval.MINUTE_5)
    bar_repo.count.return_value = 100

    result = await handler.get_sync_status()

    assert result[0].last_sync_at == to_utc_iso(sync_dt)


# get_symbol_sync_status — single symbol/interval lookup


@pytest.mark.asyncio
async def test_returns_is_stuck_field_populated(handler, sync_status_repo, bar_repo) -> None:
    sync_status_repo.find_one.return_value = _status("5m", last_bar_age_seconds=3600)
    bar_repo.get_latest.return_value = _bar(NOW - timedelta(seconds=2000), Interval.MINUTE_5)
    bar_repo.count.return_value = 100

    result = await handler.get_symbol_sync_status(
        SYMBOL,
        "5m",
    )

    # 5m cadence 300s × 3 = 900s; bar age 2000s > 900s → stuck
    assert result.is_stuck is True


@pytest.mark.asyncio
async def test_uses_bars_for_count_and_last_bar(handler, sync_status_repo, bar_repo) -> None:
    fresh_dt = NOW - timedelta(seconds=60)
    sync_status_repo.find_one.return_value = _status("1h", last_bar_age_seconds=7200, bar_count=999)
    bar_repo.get_latest.return_value = _bar(fresh_dt, Interval.HOUR_1)
    bar_repo.count.return_value = 5907

    result = await handler.get_symbol_sync_status(
        SYMBOL,
        "1h",
    )

    assert result.bar_count == 5907  # ← bars
    assert result.last_bar_at == to_utc_iso(fresh_dt)
    assert result.is_stuck is False


@pytest.mark.asyncio
async def test_not_found_raises(handler, sync_status_repo, bar_repo) -> None:
    sync_status_repo.find_one.return_value = None

    with pytest.raises(NotFoundError):
        await handler.get_symbol_sync_status(
            SYMBOL,
            "5m",
        )

    bar_repo.get_latest.assert_not_called()
    bar_repo.count.assert_not_called()


@pytest.mark.asyncio
async def test_no_bars_yet_returns_not_stuck_single_symbol(
    handler,
    sync_status_repo,
    bar_repo,
) -> None:
    sync_status_repo.find_one.return_value = _status("5m", last_bar_age_seconds=60)
    bar_repo.get_latest.return_value = None
    bar_repo.count.return_value = 0

    result = await handler.get_symbol_sync_status(
        SYMBOL,
        "5m",
    )

    assert result.is_stuck is False
    assert result.bar_count == 0
    assert result.last_bar_at is None


@pytest.mark.asyncio
async def test_status_and_error_from_sync_status(handler, sync_status_repo, bar_repo) -> None:
    s = _status("5m", last_bar_age_seconds=60)
    s.status = "error"
    s.error_message = "TV REST timeout"
    sync_status_repo.find_one.return_value = s
    bar_repo.get_latest.return_value = _bar(NOW - timedelta(seconds=60), Interval.MINUTE_5)
    bar_repo.count.return_value = 100

    result = await handler.get_symbol_sync_status(
        SYMBOL,
        "5m",
    )

    assert result.status == "error"
    assert result.error_message == "TV REST timeout"
