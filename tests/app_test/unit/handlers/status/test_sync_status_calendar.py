"""Freshness and anomaly gating follow the symbol's trading calendar.

A market that is shut is not falling behind. Without these, the calendar
argument threaded through `_is_stuck` and `emit_no_progress` could be ignored
entirely and every other test would still pass, because the 24/7 calendar makes
`previous_close` the identity and `is_open` always true.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import structlog

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.calendars.cme_globex_calendar_adapter import CmeGlobexCalendarAdapter
from pocketquant.engine.market_data.data_lag_service import FeedState
from pocketquant.engine.market_data.sync_internals.anomaly_log import emit_no_progress
from pocketquant.engine.market_data.sync_status_service import (
    GetSyncStatusQuery,
    SyncStatusQueryService,
    _Feed,
    _is_stuck,
)

CALENDAR = Continuous24x7Calendar()
CME = CmeGlobexCalendarAdapter()


class _ClosedCalendar(Continuous24x7Calendar):
    """A market that is shut right now, with its last close an hour ago."""

    def is_open(self, instant: datetime) -> bool:
        return False

    def previous_close(self, instant: datetime) -> datetime:
        return instant - timedelta(hours=1)


_HEALTHY_FEED = _Feed(lag_seconds=0, state=FeedState.OK)


class TestStucknessIsMeasuredToTheLastClose:
    def test_a_bar_from_just_before_the_close_is_not_stuck(self) -> None:
        now = datetime.now(UTC)
        closed = _ClosedCalendar()
        # Ten minutes before the close an hour ago: ancient by wall clock,
        # current by the calendar.
        last_bar = closed.previous_close(now) - timedelta(minutes=10)

        assert _is_stuck(last_bar, Interval.MINUTE_5.value, closed, _HEALTHY_FEED, now) is False
        # The same bar against a market that never closes is plainly stale.
        assert _is_stuck(last_bar, Interval.MINUTE_5.value, CALENDAR, _HEALTHY_FEED, now) is True

    def test_a_bar_from_long_before_the_close_is_still_stuck(self) -> None:
        now = datetime.now(UTC)
        closed = _ClosedCalendar()
        last_bar = closed.previous_close(now) - timedelta(hours=5)

        assert _is_stuck(last_bar, Interval.MINUTE_5.value, closed, _HEALTHY_FEED, now) is True


class TestNoProgressIsSilentWhileTheMarketIsShut:
    def _emit(self, calendar) -> list[dict]:
        with structlog.testing.capture_logs() as logs:
            emit_no_progress(
                "ES1!:CME_MINI",
                Interval.MINUTE_1,
                bars_fetched=0,
                filtered_misaligned=0,
                filtered_existing=0,
                attempts=3,
                streak=1,
                latest_bar=Bar(
                    symbol="ES1!:CME_MINI",
                    interval=Interval.MINUTE_1,
                    datetime=datetime.now(UTC) - timedelta(hours=9),
                    open=1.0,
                    high=1.0,
                    low=1.0,
                    close=1.0,
                    volume=1.0,
                ),
                calendar=calendar,
            )
        return logs

    def test_closed_market_logs_debug_not_warning(self) -> None:
        logs = self._emit(_ClosedCalendar())

        assert [e["event"] for e in logs] == ["market_data.sync.skipped_closed"]
        assert logs[0]["log_level"] == "debug"

    def test_open_market_still_warns(self) -> None:
        logs = self._emit(CALENDAR)

        events = [e["event"] for e in logs]
        assert "market_data.sync.skipped_closed" not in events
        assert "market_data.sync.no_progress" in events


@pytest.mark.asyncio
async def test_status_reports_whether_the_market_is_open() -> None:
    status = AsyncMock()
    status.symbol = "ES1!:CME_MINI"
    status.interval = Interval.MINUTE_1.value
    status.status = "completed"
    status.bar_count = 10
    status.last_sync_at = None
    status.last_bar_at = None
    status.error_message = None
    status.consecutive_empty_fetches = 0

    sync_status_repo = AsyncMock()
    sync_status_repo.find_all = AsyncMock(return_value=[status])
    bar_repo = AsyncMock()
    bar_repo.get_latest = AsyncMock(return_value=None)
    bar_repo.count = AsyncMock(return_value=10)

    factory = AsyncMock()
    factory.for_symbol = AsyncMock(return_value=_ClosedCalendar())
    closed_service = SyncStatusQueryService(sync_status_repo, bar_repo, factory)

    open_factory = AsyncMock()
    open_factory.for_symbol = AsyncMock(return_value=CALENDAR)
    open_service = SyncStatusQueryService(sync_status_repo, bar_repo, open_factory)

    closed = await closed_service.get_sync_status(GetSyncStatusQuery())
    opened = await open_service.get_sync_status(GetSyncStatusQuery())

    assert closed[0].is_market_open is False
    assert opened[0].is_market_open is True
