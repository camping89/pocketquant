# The API publishes each week as UTC segments ("Mon, 20:57:59"), each end inclusive to
# the second. Adjacent enabled segments are one session: the API splits a session at
# points such as 22:01:59/22:02:00 that are not gaps.
#
# Sessions are held in America/New_York because they follow the US market day: the UTC
# tables were recorded under EDT and move one hour later in UTC when US DST ends.
#
# Bars sit on the UTC grid (D1 at 00:00Z, H4 at 08:00Z), except that a week opens on
# Sunday 00:00Z (prod returned W1 candles at Sunday midnight).

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from pocketquant.core.domain.bar.services.bar_builder_domain_service import get_bar_start
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.value_objects import (
    CALENDAR_EXNESS_CRYPTO,
    CALENDAR_EXNESS_FX,
    CALENDAR_EXNESS_XAUUSD,
)

_UTC = ZoneInfo("UTC")
_SESSION_TZ = ZoneInfo("America/New_York")
_RECORDED_AT = datetime(2026, 10, 13, tzinfo=UTC)
_REFERENCE_WEEK = datetime(2026, 10, 11, tzinfo=UTC)  # a Sunday
_DAY_INDEX = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
_SECOND = timedelta(seconds=1)
_MINUTE = timedelta(minutes=1)
_WEEK = timedelta(weeks=1)
_WEEK_SECONDS = 7 * 86400


def _session(mode: str, start: str, end: str) -> dict[str, str]:
    return {"trade_mode": mode, "week_start_time": start, "week_end_time": end}


_ON, _OFF = "enabled", "trading_disabled"

# Recorded in UTC from getInstrumentCondition on 2026-10-13, under EDT.
_EURUSD_SESSIONS: list[dict[str, str]] = [
    _session(_OFF, "Sun, 00:00:00", "Sun, 21:04:59"),
    _session(_ON, "Sun, 21:05:00", "Sun, 23:59:59"),
    _session(_ON, "Mon, 00:00:00", "Mon, 23:59:59"),
    _session(_ON, "Tue, 00:00:00", "Tue, 23:59:59"),
    _session(_ON, "Wed, 00:00:00", "Wed, 23:59:59"),
    _session(_ON, "Thu, 00:00:00", "Thu, 23:59:59"),
    _session(_ON, "Fri, 00:00:00", "Fri, 20:58:59"),
    _session(_OFF, "Fri, 20:59:00", "Fri, 23:59:59"),
    _session(_OFF, "Sat, 00:00:00", "Sat, 23:59:59"),
]
_XAUUSD_SESSIONS: list[dict[str, str]] = [
    _session(_OFF, "Sun, 00:00:00", "Sun, 22:01:29"),
    _session(_ON, "Sun, 22:01:30", "Sun, 22:04:59"),
    _session(_ON, "Sun, 22:05:00", "Sun, 23:59:59"),
    _session(_ON, "Mon, 00:00:00", "Mon, 20:57:59"),
    _session(_OFF, "Mon, 20:58:00", "Mon, 22:00:29"),
    _session(_ON, "Mon, 22:00:30", "Mon, 22:01:59"),
    _session(_ON, "Mon, 22:02:00", "Mon, 23:59:59"),
    _session(_ON, "Tue, 00:00:00", "Tue, 20:57:59"),
    _session(_OFF, "Tue, 20:58:00", "Tue, 22:00:29"),
    _session(_ON, "Tue, 22:00:30", "Tue, 22:01:59"),
    _session(_ON, "Tue, 22:02:00", "Tue, 23:59:59"),
    _session(_ON, "Wed, 00:00:00", "Wed, 20:57:59"),
    _session(_OFF, "Wed, 20:58:00", "Wed, 22:00:29"),
    _session(_ON, "Wed, 22:00:30", "Wed, 22:01:59"),
    _session(_ON, "Wed, 22:02:00", "Wed, 23:59:59"),
    _session(_ON, "Thu, 00:00:00", "Thu, 20:57:59"),
    _session(_OFF, "Thu, 20:58:00", "Thu, 22:00:29"),
    _session(_ON, "Thu, 22:00:30", "Thu, 22:01:59"),
    _session(_ON, "Thu, 22:02:00", "Thu, 23:59:59"),
    _session(_ON, "Fri, 00:00:00", "Fri, 20:57:59"),
    _session(_OFF, "Fri, 20:58:00", "Fri, 23:59:59"),
    _session(_OFF, "Sat, 00:00:00", "Sat, 23:59:59"),
]
_BTCUSD_SESSIONS: list[dict[str, str]] = [
    _session(_ON, f"{day}, 00:00:00", f"{day}, 23:59:59")
    for day in ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
]


def exness_bar_start(instant: datetime, interval: Interval) -> datetime:
    instant = instant.astimezone(UTC)
    if interval == Interval.WEEK_1:
        midnight = instant.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight - timedelta(days=(midnight.weekday() + 1) % 7)
    return get_bar_start(instant, interval)


def _week_offset(text: str) -> int:
    day, clock = (part.strip() for part in text.split(","))
    hours, minutes, seconds = (int(p) for p in clock.split(":"))
    return _DAY_INDEX[day] * 86400 + hours * 3600 + minutes * 60 + seconds


def _shifted(start: int, end: int, shift: int) -> list[tuple[int, int]]:
    pieces = []
    for week in (-_WEEK_SECONDS, 0, _WEEK_SECONDS):
        lo, hi = max(start + shift + week, 0), min(end + shift + week, _WEEK_SECONDS)
        if lo < hi:
            pieces.append((lo, hi))
    return pieces


def _monday(instant: datetime) -> datetime:
    midnight = _wall_time(instant).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=midnight.weekday())


def _wall_time(instant: datetime) -> datetime:
    return instant.astimezone(_SESSION_TZ).replace(tzinfo=None)


def _utc(wall_time: datetime) -> datetime:
    return wall_time.replace(tzinfo=_SESSION_TZ).astimezone(UTC)


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


class ExnessSessionCalendarAdapter(ITradingCalendarPort):
    def __init__(self, calendar_id: str, week_sessions: list[dict[str, str]]) -> None:
        self._calendar_id = calendar_id
        recorded_offset = _RECORDED_AT.astimezone(_SESSION_TZ).utcoffset() or timedelta()
        shift = int(recorded_offset.total_seconds())
        spans = sorted(
            piece
            for s in week_sessions
            if s["trade_mode"] == _ON
            for piece in _shifted(
                _week_offset(s["week_start_time"]), _week_offset(s["week_end_time"]) + 1, shift
            )
        )
        merged: list[tuple[int, int]] = []
        for start, end in spans:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        # [start, end) in seconds from Monday 00:00 New York wall time.
        self._segments = tuple(merged)

    @property
    def calendar_id(self) -> str:
        return self._calendar_id

    # Merged across week boundaries, so a session running over New York Monday midnight
    # is one span.
    def _spans(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        spans: list[tuple[datetime, datetime]] = []
        week, last = _monday(start) - _WEEK, _monday(end) + _WEEK
        while week <= last:
            for offset_start, offset_end in self._segments:
                lo = _utc(week + timedelta(seconds=offset_start))
                hi = _utc(week + timedelta(seconds=offset_end))
                if spans and spans[-1][1] == lo:
                    spans[-1] = (spans[-1][0], hi)
                else:
                    spans.append((lo, hi))
            week += _WEEK
        return spans

    def is_open(self, instant: datetime) -> bool:
        offset = (_wall_time(instant) - _monday(instant)).total_seconds()
        return any(start <= offset < end for start, end in self._segments)

    def session_date(self, instant: datetime) -> date:
        return instant.astimezone(UTC).date()

    def _day_spans(self, session_date: date) -> list[tuple[datetime, datetime]]:
        lo = _midnight(session_date)
        hi = lo + timedelta(days=1)
        return [(max(s, lo), min(e, hi)) for s, e in self._spans(lo, lo) if s < hi and e > lo]

    # Midnight UTC even on a Sunday whose first trade comes in the evening: it is the open
    # of that date's D1 candle, which the integrity check compares against.
    def session_open(self, session_date: date) -> datetime:
        if not self._day_spans(session_date):
            raise KeyError(f"{session_date.isoformat()} is not an {self._calendar_id} session")
        return _midnight(session_date)

    def session_close(self, session_date: date) -> datetime:
        spans = self._day_spans(session_date)
        if not spans:
            raise KeyError(f"{session_date.isoformat()} is not an {self._calendar_id} session")
        return spans[-1][1] - _SECOND

    def previous_close(self, instant: datetime) -> datetime:
        if self.is_open(instant):
            return instant
        instant = instant.astimezone(UTC)
        ends = [end for _, end in self._spans(instant, instant) if end <= instant]
        if not ends:
            raise KeyError(f"No {self._calendar_id} session before {instant.isoformat()}")
        return max(ends) - _SECOND

    # An open second inside the window, not merely a date in it: a daily check at Sunday
    # 00:00Z must not expect Sunday's candle, which exists only once Sunday trading starts.
    def sessions(self, start: datetime, end: datetime) -> list[date]:
        start, end = start.astimezone(UTC), end.astimezone(UTC)
        days: set[date] = set()
        for span_start, span_end in self._spans(start, end):
            lo, hi = max(span_start, start), min(span_end, end + _SECOND)
            if lo >= hi:
                continue
            day = lo.date()
            while day <= (hi - _SECOND).date():
                days.add(day)
                day += timedelta(days=1)
        return sorted(days)

    # Overlap, not containment: 22:00 counts when trading resumes at 22:00:30, and 20:57
    # counts when it stops at 20:57:59.
    def trading_minutes(self, start: datetime, end: datetime) -> list[datetime]:
        spans = self._spans(start, end)
        minutes: list[datetime] = []
        index = 0
        for i in range(int((end - start) // _MINUTE)):
            minute = start + i * _MINUTE
            while index < len(spans) and spans[index][1] <= minute:
                index += 1
            if index < len(spans) and spans[index][0] < minute + _MINUTE:
                minutes.append(minute)
        return minutes

    def bar_start(self, instant: datetime, interval: Interval) -> datetime:
        return exness_bar_start(instant, interval)

    # Bar opens counted in one Sunday-to-Sunday week, not divided out of open hours: FX
    # trades about 5 days a week yet prints 6 daily bars (Sunday evening has its own).
    def periods_per_year(self, interval: Interval) -> float:
        minutes = self.trading_minutes(_REFERENCE_WEEK, _REFERENCE_WEEK + _WEEK)
        return float(len({self.bar_start(m, interval) for m in minutes}) * 52)


EXNESS_CALENDARS: tuple[ExnessSessionCalendarAdapter, ...] = (
    ExnessSessionCalendarAdapter(CALENDAR_EXNESS_FX, _EURUSD_SESSIONS),
    ExnessSessionCalendarAdapter(CALENDAR_EXNESS_XAUUSD, _XAUUSD_SESSIONS),
    ExnessSessionCalendarAdapter(CALENDAR_EXNESS_CRYPTO, _BTCUSD_SESSIONS),
)
