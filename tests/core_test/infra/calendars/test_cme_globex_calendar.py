"""CME Globex session edges: DST, weekends, halts, holidays and early closes.

These are the cases where a fixed UTC offset would look right for months and
then be wrong by an hour, or where a naive weekday check would invent a session
that does not exist. Expectations are stated as UTC instants because that is
what every caller receives.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from pocketquant.core.domain.shared.enums import Interval
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


class TestEveryCallerSurvivesTheWeekendGap:
    """Between Friday's close and Sunday's open there is no session at all.

    The session-lookup window used to reach one day either side, which is
    shorter than the gap it has to clear: on a Saturday there was no session
    ahead of the instant and on a Sunday morning none behind it, so the lookup
    raised instead of answering. Every caller below runs on that gap in
    production — ``previous_close`` and ``is_open`` are the pair the sync job's
    closed-market gate gets for every symbol, and that call sits outside its
    per-symbol error handling, so one raise would have stopped the whole cycle
    including the crypto symbols.
    """

    # Friday noon through Monday noon UTC: a full weekend from both sides.
    START = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
    HOURS = 72

    def _instants(self):
        return [self.START + timedelta(hours=h) for h in range(self.HOURS)]

    def test_the_sync_gate_never_raises_across_a_weekend(
        self, calendar: CmeGlobexCalendarAdapter
    ) -> None:
        grace = timedelta(minutes=1)
        for instant in self._instants():
            # Exactly what sync_jobs._sync_by_intervals evaluates per symbol.
            # The value is not the point — reaching it without raising is.
            skip = not (
                calendar.is_open(instant) or (instant - calendar.previous_close(instant)) <= grace
            )
            assert isinstance(skip, bool)

    def test_bar_start_and_session_date_never_raise_across_a_weekend(
        self, calendar: CmeGlobexCalendarAdapter
    ) -> None:
        for instant in self._instants():
            for interval in (Interval.MINUTE_1, Interval.HOUR_1, Interval.DAY_1):
                calendar.bar_start(instant, interval)
            calendar.session_date(instant)

    def test_the_gap_resolves_to_the_sessions_on_either_side(
        self, calendar: CmeGlobexCalendarAdapter
    ) -> None:
        saturday = datetime(2026, 9, 19, 3, 0, tzinfo=UTC)

        # Friday's session closed at 16:00 Chicago; Monday's opens Sunday evening.
        assert calendar.previous_close(saturday) == datetime(2026, 9, 18, 21, 0, tzinfo=UTC)
        assert calendar.session_date(saturday) == date(2026, 9, 21)
        assert calendar.is_open(saturday) is False


class TestNoIntradayEquityIndexHalt:
    """ES, NQ and YM trade straight through 15:15-15:30 Chicago.

    CME eliminated that pause for its equity-index futures effective trade date
    2021-06-28, yet many hours pages still list it, and it was once modelled
    here from one of them. Modelling a halt that does not exist makes the sync
    gate skip fifteen live minutes a day, the cascade expect 45 bars of an hour
    that holds 60, and the hourly annualization count 62 hours short. Measured
    against TradingView's 1m series: every one of those minutes carries a bar.
    """

    CT = ZoneInfo("America/Chicago")

    def _at(self, hour: int, minute: int) -> datetime:
        # A plain Tuesday, no holiday and no early close.
        return datetime(2026, 9, 22, hour, minute, tzinfo=self.CT).astimezone(UTC)

    def test_the_market_is_open_through_the_former_halt(
        self, calendar: CmeGlobexCalendarAdapter
    ) -> None:
        for minute in (14, 15, 20, 29, 30):
            assert calendar.is_open(self._at(15, minute)) is True

    def test_every_minute_of_that_hour_is_a_trading_minute(
        self, calendar: CmeGlobexCalendarAdapter
    ) -> None:
        """The cascade takes a bucket's expected bar count from this."""
        minutes = calendar.trading_minutes(self._at(15, 0), self._at(16, 0))

        assert len(minutes) == 60

    def test_previous_close_is_the_instant_itself_while_trading(
        self, calendar: CmeGlobexCalendarAdapter
    ) -> None:
        assert calendar.previous_close(self._at(15, 20)) == self._at(15, 20)

    def test_the_maintenance_break_is_still_the_daily_close(
        self, calendar: CmeGlobexCalendarAdapter
    ) -> None:
        assert calendar.is_open(self._at(15, 59)) is True
        assert calendar.is_open(self._at(16, 0)) is False
        assert calendar.is_open(self._at(16, 59)) is False


class TestAWindowEndingAfterTheEveningOpen:
    """A session opens the evening before the day it is dated by.

    A window that ends between that open and UTC midnight holds trading minutes
    from the next-dated session. Counting only up to the window's own date
    reads those two hours of every evening as closed, which made feed lag read
    zero and the integrity grid expect nothing there.
    """

    def test_the_first_minutes_after_the_sunday_open_are_trading_minutes(
        self, calendar: CmeGlobexCalendarAdapter
    ) -> None:
        sunday_open = datetime(2026, 9, 20, 22, 0, tzinfo=UTC)

        minutes = calendar.trading_minutes(sunday_open, sunday_open + timedelta(minutes=5))

        assert minutes == [sunday_open + timedelta(minutes=i) for i in range(5)]

    def test_a_weekday_evening_window_spans_the_halt_and_the_reopen(
        self, calendar: CmeGlobexCalendarAdapter
    ) -> None:
        # Tuesday 20:30-22:30 UTC: 30 minutes before the 21:00 close, the halt,
        # then 30 minutes of Wednesday's session.
        start = datetime(2026, 9, 22, 20, 30, tzinfo=UTC)

        minutes = calendar.trading_minutes(start, start + timedelta(hours=2))

        assert len(minutes) == 60
