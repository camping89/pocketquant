"""CME Globex session edges: DST, weekends, halts, holidays and early closes.

These are the cases where a fixed UTC offset would look right for months and
then be wrong by an hour, or where a naive weekday check would invent a session
that does not exist. Expectations are stated as UTC instants because that is
what every caller receives.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from pocketquant.core.infra.calendars.cme_globex_calendar_adapter import CmeGlobexCalendarAdapter


@pytest.fixture(scope="module")
def calendar() -> CmeGlobexCalendarAdapter:
    return CmeGlobexCalendarAdapter()


def test_spring_forward_session_open(calendar: CmeGlobexCalendarAdapter) -> None:
    # 17:00 Chicago on the evening the clocks go forward is 22:00 UTC.
    assert calendar.session_open(date(2026, 3, 9)) == datetime(2026, 3, 8, 22, 0, tzinfo=UTC)


def test_fall_back_session_open(calendar: CmeGlobexCalendarAdapter) -> None:
    # The same 17:00 Chicago open is 23:00 UTC once the clocks go back.
    assert calendar.session_open(date(2026, 11, 2)) == datetime(2026, 11, 1, 23, 0, tzinfo=UTC)


def test_sunday_reopen(calendar: CmeGlobexCalendarAdapter) -> None:
    monday_open = calendar.session_open(date(2026, 6, 8))

    assert calendar.is_open(monday_open - timedelta(hours=2)) is False
    assert calendar.is_open(monday_open + timedelta(hours=1)) is True


def test_weekend_closed(calendar: CmeGlobexCalendarAdapter) -> None:
    assert calendar.is_open(datetime(2026, 6, 6, 12, 0, tzinfo=UTC)) is False


def test_daily_halt_closed(calendar: CmeGlobexCalendarAdapter) -> None:
    during_halt = calendar.session_close(date(2026, 6, 10)) + timedelta(minutes=30)

    assert calendar.is_open(during_halt) is False


def test_holiday_is_not_a_session(calendar: CmeGlobexCalendarAdapter) -> None:
    sessions = calendar.sessions(
        datetime(2026, 12, 20, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC)
    )

    assert date(2026, 12, 25) not in sessions


def test_juneteenth_early_close(calendar: CmeGlobexCalendarAdapter) -> None:
    juneteenth = date(2026, 6, 19)

    span = calendar.session_close(juneteenth) - calendar.session_open(juneteenth)

    assert span < timedelta(hours=23)


def test_session_spans_utc_midnight(calendar: CmeGlobexCalendarAdapter) -> None:
    session = date(2026, 6, 10)

    assert calendar.session_open(session).date() != calendar.session_close(session).date()
