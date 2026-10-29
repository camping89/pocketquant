"""Trading-calendar port — when a market is open, and what a session is worth.

Every ``datetime`` crossing this interface is a timezone-aware UTC instant, in
both directions. Session boundaries are derived from the exchange-local wall
time converted through ``zoneinfo``, never by adding a fixed offset: Exness
sessions follow New York time, so the XAUUSD daily break starts at 20:58 UTC
under US daylight saving and at 21:58 UTC after it ends.

``session_date`` is the calendar's own day key, which need not be the UTC date.
The Exness calendars key by the UTC date, so a Sunday session is dated Sunday
even though its first trade comes in the evening.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

from pocketquant.core.domain.shared.enums import Interval


class ITradingCalendarPort(ABC):
    """The schedule a symbol trades on. One implementation per venue family."""

    @property
    @abstractmethod
    def calendar_id(self) -> str:
        """Stable identifier persisted on the symbol record."""
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
