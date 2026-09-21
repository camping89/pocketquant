"""The 24/7 calendar — crypto's schedule, expressed as an ordinary calendar.

This exists so the pipeline has exactly one code path. Every method reproduces
what the crypto path already did implicitly, so threading a calendar through the
sync, cascade, integrity and annualization math leaves crypto numbers identical.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from pocketquant.core.domain.bar.services.bar_builder_domain_service import get_bar_start
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.value_objects import CALENDAR_CRYPTO_24_7

_UTC = ZoneInfo("UTC")


class Continuous24x7Calendar(ITradingCalendarPort):
    """A market that never closes. Session date is simply the UTC date."""

    @property
    def calendar_id(self) -> str:
        return CALENDAR_CRYPTO_24_7

    @property
    def tz(self) -> ZoneInfo:
        return _UTC

    def is_open(self, instant: datetime) -> bool:
        return True

    def session_date(self, instant: datetime) -> date:
        return instant.astimezone(UTC).date()

    def session_open(self, session_date: date) -> datetime:
        return datetime(session_date.year, session_date.month, session_date.day, tzinfo=UTC)

    def session_close(self, session_date: date) -> datetime:
        return self.session_open(session_date) + timedelta(days=1)

    def previous_close(self, instant: datetime) -> datetime:
        # Identity, not an oversight: with no close to wait for, the most recent
        # instant a bar could have closed is now. This is what keeps crypto
        # freshness arithmetic byte-identical once the calendar is threaded in.
        return instant

    def sessions(self, start: datetime, end: datetime) -> list[date]:
        first = start.astimezone(UTC).date()
        last = end.astimezone(UTC).date()
        return [first + timedelta(days=i) for i in range((last - first).days + 1)]

    def trading_minutes(self, start: datetime, end: datetime) -> list[datetime]:
        minute = timedelta(minutes=1)
        return [start + i * minute for i in range(int((end - start) // minute))]

    def bar_start(self, instant: datetime, interval: Interval) -> datetime:
        # Delegated rather than reimplemented: two copies of alignment could
        # drift, and a drift here is bars silently failing is_bar_aligned.
        return get_bar_start(instant, interval)

    def periods_per_year(self, interval: Interval) -> float:
        return interval.periods_per_year
