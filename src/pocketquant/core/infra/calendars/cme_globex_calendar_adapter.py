"""CME Globex equity-index session calendar (ES, NQ, YM).

Wraps ``pandas_market_calendars`` so holiday and early-close rules — which CME
revises yearly — stay in a maintained library rather than in our code or in a
Mongo copy someone has to hand-sync against CME notices.

Two facts drive everything here. A session opens the evening *before* its own
date (17:00 Chicago), so a session spans UTC midnight and the session date is
not the UTC date. And 17:00 Chicago is 22:00 UTC in summer but 23:00 UTC in
winter, so no boundary may ever be computed by adding a fixed offset.
"""

from __future__ import annotations

import functools
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal

from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.shared.value_objects import INTERVAL_SECONDS
from pocketquant.core.domain.symbol.value_objects import CALENDAR_CME_GLOBEX_EQUITY

_CALENDAR_NAME = "CME Globex Equity"
_TZ = ZoneInfo("America/Chicago")

# Annualization is measured over a FIXED window rather than a trailing one, so
# the same backtest reports the same Sharpe whenever it is re-run.
_REFERENCE_YEAR_START = date(2025, 1, 1)
_REFERENCE_YEAR_END = date(2025, 12, 31)

_MINUTE = timedelta(minutes=1)


class CmeGlobexCalendarAdapter(ITradingCalendarPort):
    """Session boundaries for CME Globex equity-index futures, as UTC instants."""

    def __init__(self) -> None:
        self._cal = mcal.get_calendar(_CALENDAR_NAME)

    @property
    def calendar_id(self) -> str:
        return CALENDAR_CME_GLOBEX_EQUITY

    @property
    def tz(self) -> ZoneInfo:
        return _TZ

    # --- schedule access -------------------------------------------------

    @functools.lru_cache(maxsize=64)  # noqa: B019 — APP-scoped singleton, bounded by maxsize
    def _schedule(self, start: date, end: date) -> pd.DataFrame:
        """Sessions in ``[start, end]``. Cached: the cron re-asks constantly."""
        return self._cal.schedule(start_date=start, end_date=end)

    def _row(self, session_date: date) -> pd.Series:
        schedule = self._schedule(session_date, session_date)
        if schedule.empty:
            raise KeyError(f"{session_date.isoformat()} is not a CME Globex equity session")
        return schedule.iloc[0]

    @staticmethod
    def _as_utc(value: Any) -> datetime:
        """Normalise a schedule cell to a UTC ``datetime``.

        Typed loosely because indexing a pandas Series yields a union the stubs
        cannot narrow; ``pd.Timestamp`` accepts every shape the schedule holds.
        A missing boundary is raised rather than propagated: a NaT session edge
        would otherwise flow into bar alignment as a silently wrong instant.
        """
        stamp = pd.Timestamp(value)
        if stamp is pd.NaT:
            raise ValueError(f"CME Globex schedule holds no instant for {value!r}")
        # cast: the NaT guard above is the real check; pd.Timestamp's stubs do
        # not narrow through an identity comparison.
        return cast("datetime", stamp.tz_convert("UTC").to_pydatetime())

    @staticmethod
    def _session_date_of(value: Any) -> date:
        """The session date from a schedule index entry.

        The index is tz-naive calendar days, unlike the tz-aware boundary
        columns, so this must not go through ``_as_utc``.
        """
        stamp = pd.Timestamp(value)
        if stamp is pd.NaT:
            raise ValueError(f"CME Globex schedule holds no session date for {value!r}")
        return cast("date", stamp.date())

    # --- port ------------------------------------------------------------

    def session_open(self, session_date: date) -> datetime:
        return self._as_utc(self._row(session_date)["market_open"])

    def session_close(self, session_date: date) -> datetime:
        return self._as_utc(self._row(session_date)["market_close"])

    def session_date(self, instant: datetime) -> date:
        """The session owning ``instant``.

        During the daily maintenance halt the instant belongs to no session, so
        this returns the date of the NEXT session to open — callers asking "which
        session is this?" during a halt want the one about to start, not the one
        that just ended.
        """
        instant = instant.astimezone(UTC)
        for candidate, row in self._window_rows(instant):
            if self._as_utc(row["market_open"]) <= instant < self._as_utc(row["market_close"]):
                return candidate
        for candidate, row in self._window_rows(instant):
            if instant < self._as_utc(row["market_open"]):
                return candidate
        raise KeyError(f"No CME Globex equity session found for {instant.isoformat()}")

    def is_open(self, instant: datetime) -> bool:
        instant = instant.astimezone(UTC)
        return any(
            self._as_utc(row["market_open"]) <= instant < self._as_utc(row["market_close"])
            for _, row in self._window_rows(instant)
        )

    def previous_close(self, instant: datetime) -> datetime:
        """The most recent instant a bar could have closed, at or before ``instant``."""
        instant = instant.astimezone(UTC)
        closes = [
            self._as_utc(row["market_close"])
            for _, row in self._window_rows(instant)
            if self._as_utc(row["market_open"]) <= instant
        ]
        if not closes:
            raise KeyError(f"No CME Globex equity session at or before {instant.isoformat()}")
        return min(instant, max(closes))

    def sessions(self, start: datetime, end: datetime) -> list[date]:
        schedule = self._schedule(start.astimezone(UTC).date(), end.astimezone(UTC).date())
        return [self._session_date_of(ts) for ts in schedule.index]

    def trading_minutes(self, start: datetime, end: datetime) -> list[datetime]:
        start = start.astimezone(UTC)
        end = end.astimezone(UTC)
        minutes: list[datetime] = []
        # Reach back a day: a session open the evening before can still be
        # contributing minutes inside the requested window.
        schedule = self._schedule(start.date() - timedelta(days=1), end.date())
        for _, row in schedule.iterrows():
            lower = max(start, self._as_utc(row["market_open"]))
            upper = min(end, self._as_utc(row["market_close"]))
            if lower >= upper:
                continue
            minutes.extend(lower + i * _MINUTE for i in range(int((upper - lower) // _MINUTE)))
        return minutes

    def bar_start(self, instant: datetime, interval: Interval) -> datetime:
        instant = instant.astimezone(UTC)
        session = self.session_date(instant)

        if interval == Interval.DAY_1:
            return self.session_open(session)

        if interval == Interval.WEEK_1:
            week_start = session - timedelta(days=session.weekday())
            week_sessions = self._schedule(week_start, session)
            if week_sessions.empty:
                return self.session_open(session)
            return self._as_utc(week_sessions.iloc[0]["market_open"])

        # Intraday bars are counted from the session open, not from the epoch,
        # so a bar boundary never straddles the maintenance halt.
        open_instant = self.session_open(session)
        if instant < open_instant:
            return open_instant
        step = timedelta(seconds=INTERVAL_SECONDS[interval])
        elapsed = instant - open_instant
        return open_instant + (elapsed // step) * step

    def periods_per_year(self, interval: Interval) -> float:
        """Bars per year, measured over the fixed 2025 reference window."""
        return self._periods_per_year(interval)

    @functools.lru_cache(maxsize=16)  # noqa: B019 — APP-scoped singleton, bounded by maxsize
    def _periods_per_year(self, interval: Interval) -> float:
        schedule = self._schedule(_REFERENCE_YEAR_START, _REFERENCE_YEAR_END)
        session_count = len(schedule.index)

        if interval == Interval.DAY_1:
            return float(session_count)
        if interval == Interval.WEEK_1:
            return session_count / 5.0

        total_minutes = sum(
            (self._as_utc(row["market_close"]) - self._as_utc(row["market_open"])) // _MINUTE
            for _, row in schedule.iterrows()
        )
        return total_minutes / (INTERVAL_SECONDS[interval] / 60.0)

    # --- internals -------------------------------------------------------

    def _window_rows(self, instant: datetime):
        """Session rows that could contain ``instant``, allowing for the evening open."""
        day = instant.date()
        schedule = self._schedule(day - timedelta(days=1), day + timedelta(days=1))
        return [(self._session_date_of(ts), row) for ts, row in schedule.iterrows()]
