from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

from pocketquant.core.domain.shared.enums import Interval


# Every datetime in or out is an aware UTC instant. Session bounds come from local wall
# time through zoneinfo, never a fixed offset: the XAUUSD daily break starts at 20:58 UTC
# under US DST and 21:58 UTC after it. session_date is the calendar's own day key, which
# need not be the UTC date.
class ITradingCalendarPort(ABC):
    @property
    @abstractmethod
    def calendar_id(self) -> str: ...

    @abstractmethod
    def is_open(self, instant: datetime) -> bool: ...

    @abstractmethod
    def session_date(self, instant: datetime) -> date: ...

    @abstractmethod
    def session_open(self, session_date: date) -> datetime: ...

    @abstractmethod
    def session_close(self, session_date: date) -> datetime: ...

    # For 24/7 this is instant itself, which keeps now - last_bar freshness unchanged.
    @abstractmethod
    def previous_close(self, instant: datetime) -> datetime: ...

    @abstractmethod
    def sessions(self, start: datetime, end: datetime) -> list[date]: ...

    @abstractmethod
    def trading_minutes(self, start: datetime, end: datetime) -> list[datetime]: ...

    @abstractmethod
    def bar_start(self, instant: datetime, interval: Interval) -> datetime: ...

    @abstractmethod
    def periods_per_year(self, interval: Interval) -> float: ...
