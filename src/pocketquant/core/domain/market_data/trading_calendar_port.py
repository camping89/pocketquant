"""Trading-calendar port — when a market is open, and what a session is worth.

Every ``datetime`` crossing this interface is a timezone-aware UTC instant, in
both directions. Session boundaries are derived from the exchange-local wall
time converted through ``zoneinfo``, never by adding a fixed offset: CME's open
is 17:00 Chicago time all year, which is 22:00 UTC in summer and 23:00 UTC in
winter.

``session_date`` is the exchange's own day key, which is not the UTC date. A CME
session opens the previous evening, so the instant 2026-06-10T02:00Z belongs to
session date 2026-06-10 even though it is still 2026-06-09 in Chicago.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pocketquant.core.domain.shared.enums import Interval


class ITradingCalendarPort(ABC):
    """The schedule a symbol trades on. One implementation per venue family."""

    @property
    @abstractmethod
    def calendar_id(self) -> str:
        """Stable identifier persisted on the symbol record."""
        ...

    @property
    @abstractmethod
    def tz(self) -> ZoneInfo:
        """The exchange's own timezone, which local wall times are expressed in."""
        ...

    @abstractmethod
    def is_open(self, instant: datetime) -> bool:
        """True when ``instant`` falls inside a trading session."""
        ...

    @abstractmethod
    def session_date(self, instant: datetime) -> date:
        """The exchange-calendar day key owning ``instant``."""
        ...

    @abstractmethod
    def session_open(self, session_date: date) -> datetime:
        """UTC instant at which ``session_date`` opens."""
        ...

    @abstractmethod
    def session_close(self, session_date: date) -> datetime:
        """UTC instant at which ``session_date`` closes."""
        ...

    @abstractmethod
    def previous_close(self, instant: datetime) -> datetime:
        """The most recent instant at which a bar could have closed.

        For a 24/7 calendar this is ``instant`` itself, which is what keeps
        ``now - last_bar`` freshness arithmetic unchanged for crypto.
        """
        ...

    @abstractmethod
    def sessions(self, start: datetime, end: datetime) -> list[date]:
        """Every session date in ``[start, end]``, ascending."""
        ...

    @abstractmethod
    def trading_minutes(self, start: datetime, end: datetime) -> list[datetime]:
        """Every minute-open instant in ``[start, end)`` that is a trading minute."""
        ...

    @abstractmethod
    def bar_start(self, instant: datetime, interval: Interval) -> datetime:
        """The open instant of the ``interval`` bar containing ``instant``."""
        ...

    @abstractmethod
    def periods_per_year(self, interval: Interval) -> float:
        """Bars of ``interval`` in one year, for annualizing per-bar statistics."""
        ...
