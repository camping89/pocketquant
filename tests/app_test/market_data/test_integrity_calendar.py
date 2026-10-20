"""The integrity grid belongs to the symbol's calendar.

A dense arithmetic grid reports every closed hour as a missing bar, which for a
futures symbol means the repair job resyncing a market that was simply shut.
These pin that the expected instants come from the calendar instead, and that
weekly bars are declined rather than guessed at.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.bar.entities import SOURCE_REST_REPAIR
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.calendars.cme_globex_calendar_adapter import CmeGlobexCalendarAdapter
from pocketquant.core.infra.calendars.exness_session_calendar_adapter import EXNESS_CALENDARS
from pocketquant.engine.market_data.app_services.integrity_jobs import (
    check_integrity,
    repair_integrity,
)
from pocketquant.engine.market_data.sync_service import SyncService

CALENDAR = Continuous24x7Calendar()
CME = CmeGlobexCalendarAdapter()


def _empty_bar_repo() -> MagicMock:
    """A symbol with no stored bars at all — every expected instant is missing."""
    repo = MagicMock()
    repo.find_datetimes = AsyncMock(return_value=[])
    repo.delete_many_by_ids = AsyncMock(return_value=0)
    return repo


@pytest.mark.asyncio
async def test_a_session_calendar_expects_far_fewer_hours_than_a_247_one() -> None:
    """Over a week, CME is shut at weekends and for one hour a day."""
    repo = _empty_bar_repo()

    continuous = await check_integrity("BTCUSDT:BINANCE", Interval.HOUR_1, repo, CALENDAR, 7)
    session = await check_integrity("ES1!:TRADINGVIEW", Interval.HOUR_1, repo, CME, 7)

    # 7 days of hours on a market that never closes.
    assert continuous["missing_count"] == 7 * 24
    # Weekends and the daily maintenance halt are not gaps.
    assert 0 < session["missing_count"] < continuous["missing_count"]


@pytest.mark.asyncio
async def test_daily_grid_is_session_opens_not_utc_midnights() -> None:
    repo = _empty_bar_repo()

    session = await check_integrity("ES1!:TRADINGVIEW", Interval.DAY_1, repo, CME, 7)

    # Five sessions in a week, not seven days.
    assert session["missing_count"] <= 6
    assert session["missing_count"] >= 4


@pytest.mark.asyncio
@pytest.mark.parametrize("calendar", [CALENDAR, CME, *EXNESS_CALENDARS])
@pytest.mark.parametrize("interval", [Interval.DAY_1, Interval.HOUR_4])
async def test_every_closed_bar_stored_is_no_gap(calendar: Any, interval: Interval) -> None:
    """The bar still in progress cannot be stored yet, so it is not missing."""
    now = datetime.now(UTC)
    in_progress = calendar.bar_start(now, interval)
    # Every 15th trading minute still lands in every bar (none is that short),
    # and keeps the CME calendar's per-instant lookups fast.
    minutes = calendar.trading_minutes(now - timedelta(days=9), now)[::15]
    closed = {calendar.bar_start(minute, interval) for minute in minutes} - {in_progress}
    repo = _empty_bar_repo()
    repo.find_datetimes = AsyncMock(
        return_value=[{"_id": str(i), "datetime": instant} for i, instant in enumerate(closed)]
    )

    report = await check_integrity("X:Y", interval, repo, calendar, 7)

    assert report["missing_count"] == 0, report["gap_ranges"]


@pytest.mark.asyncio
async def test_weekly_check_declines_rather_than_guessing() -> None:
    repo = _empty_bar_repo()

    report = await check_integrity("BTCUSDT:BINANCE", Interval.WEEK_1, repo, CALENDAR, 30)

    assert report["skipped_reason"] == "weekly_convention"
    assert report["missing_count"] == 0
    assert report["gap_ranges"] == []


@pytest.mark.asyncio
async def test_weekly_repair_resyncs_nothing() -> None:
    repo = _empty_bar_repo()
    sync_service = MagicMock(spec=SyncService)
    sync_service.sync_one = AsyncMock()

    result = await repair_integrity(
        symbol="BTCUSDT:BINANCE",
        interval=Interval.WEEK_1,
        bar_repo=repo,
        sync_service=sync_service,
        calendar=CALENDAR,
        source=SOURCE_REST_REPAIR,
        days_back=30,
    )

    assert result["skipped_reason"] == "weekly_convention"
    assert result["gaps_resynced"] == 0
    sync_service.sync_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_misalignment_is_judged_against_the_symbols_calendar() -> None:
    """A UTC-midnight daily bar is aligned for crypto and misaligned for CME."""
    repo = _empty_bar_repo()
    repo.find_datetimes = AsyncMock(
        return_value=[{"_id": "abc", "datetime": datetime(2026, 6, 10, 0, 0, tzinfo=UTC)}]
    )

    continuous = await check_integrity("BTCUSDT:BINANCE", Interval.DAY_1, repo, CALENDAR, 7)
    session = await check_integrity("ES1!:TRADINGVIEW", Interval.DAY_1, repo, CME, 7)

    assert continuous["misaligned_count"] == 0
    assert session["misaligned_count"] == 1
    assert session["misaligned_ids"] == ["abc"]


XAUUSD = EXNESS_CALENDARS[1]


def _first_minute(calendar: Any, *, trading: bool) -> datetime:
    """The first 1m instant in the last few days that trades, or that does not."""
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(days=6)
    open_minutes = set(calendar.trading_minutes(start, start + timedelta(days=5)))
    for i in range(5 * 24 * 60):
        minute = start + timedelta(minutes=i)
        if (minute in open_minutes) == trading:
            return minute
    raise AssertionError("no such minute in five days")


@pytest.mark.asyncio
async def test_a_1m_bar_stored_at_a_closed_minute_is_unexpected() -> None:
    closed = _first_minute(XAUUSD, trading=False)
    repo = _empty_bar_repo()
    repo.find_datetimes = AsyncMock(return_value=[{"_id": "a", "datetime": closed}])

    report = await check_integrity("XAUUSD:EXNESS", Interval.MINUTE_1, repo, XAUUSD, 7)

    assert report["misaligned_count"] == 0
    assert report["unexpected_count"] == 1
    assert report["unexpected_ranges"] == [(closed.isoformat(), closed.isoformat())]


@pytest.mark.asyncio
async def test_a_1m_bar_stored_at_an_open_minute_is_expected() -> None:
    repo = _empty_bar_repo()
    repo.find_datetimes = AsyncMock(
        return_value=[{"_id": "a", "datetime": _first_minute(XAUUSD, trading=True)}]
    )

    report = await check_integrity("XAUUSD:EXNESS", Interval.MINUTE_1, repo, XAUUSD, 7)

    assert report["unexpected_count"] == 0
    assert report["unexpected_ranges"] == []
