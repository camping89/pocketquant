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
                calendar.is_open(instant)
                or (instant - calendar.previous_close(instant)) <= grace
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


class TestTheIntradayEquityIndexHalt:
    """ES, NQ and YM pause 15:15-15:30 Chicago, just after the cash close.

    The upstream calendar models only the 16:00-17:00 maintenance break, so
    without this the pipeline believes fifteen minutes of every weekday are
    trading minutes that produce no bars. That reads downstream as a stuck
    symbol, a partial hourly bucket, and fifteen missing minutes per symbol per
    day in the nightly integrity scan.

    The halt is specific to the index products; CME's crude and gold contracts
    run straight through this window, which is why it lives in this adapter
    rather than in a shared rule.
    """

    CT = ZoneInfo("America/Chicago")

    def _at(self, hour: int, minute: int) -> datetime:
        # A plain Tuesday, no holiday and no early close.
        return datetime(2026, 9, 22, hour, minute, tzinfo=self.CT).astimezone(UTC)

    def test_the_market_is_shut_only_between_the_halt_boundaries(
        self, calendar: CmeGlobexCalendarAdapter
    ) -> None:
        assert calendar.is_open(self._at(15, 14)) is True
        assert calendar.is_open(self._at(15, 15)) is False
        assert calendar.is_open(self._at(15, 29)) is False
        assert calendar.is_open(self._at(15, 30)) is True

    def test_the_halt_is_not_counted_as_trading_minutes(
        self, calendar: CmeGlobexCalendarAdapter
    ) -> None:
        """The cascade takes a bucket's expected bar count from this."""
        minutes = calendar.trading_minutes(self._at(15, 0), self._at(16, 0))

        assert len(minutes) == 45

    def test_previous_close_holds_at_the_halt_start(
        self, calendar: CmeGlobexCalendarAdapter
    ) -> None:
        """Otherwise the gap the sync gate measures stays at zero throughout.

        ``previous_close`` returns the instant itself while a market is open,
        so without this the gate would read "it closed just now" for every one
        of the fifteen minutes and keep fetching through the whole halt.
        """
        assert calendar.previous_close(self._at(15, 20)) == self._at(15, 15)

    def test_a_dst_shift_moves_the_halt_with_the_wall_clock(
        self, calendar: CmeGlobexCalendarAdapter
    ) -> None:
        """15:15 Chicago is 20:15 UTC in summer and 21:15 UTC in winter.

        A fixed offset would look correct for months and then halt the wrong
        quarter-hour — the failure this whole adapter exists to prevent.
        """
        summer = datetime(2026, 7, 15, 15, 20, tzinfo=self.CT)
        winter = datetime(2026, 12, 15, 15, 20, tzinfo=self.CT)

        assert summer.astimezone(UTC).hour == 20
        assert winter.astimezone(UTC).hour == 21
        assert calendar.is_open(summer) is False
        assert calendar.is_open(winter) is False
