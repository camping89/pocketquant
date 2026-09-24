"""Record which trading schedule a bar belongs to, before it is persisted.

Every path that writes provider bars stamps them here, so a bar's
``calendar_id`` and ``session_date`` do not depend on which job wrote it.
"""

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval

_SESSION_KEYED = frozenset({Interval.DAY_1, Interval.WEEK_1})


def stamp_calendar(records: list[Bar], interval: Interval, calendar: ITradingCalendarPort) -> None:
    """Record which schedule each bar belongs to, and its session day key.

    The session day is only meaningful for bars that span one, so intraday
    bars are left without one rather than given the UTC date, which for a
    session opening the evening before is the wrong day.
    """
    session_keyed = interval in _SESSION_KEYED
    for bar in records:
        bar.calendar_id = calendar.calendar_id
        if session_keyed and bar.datetime is not None:
            bar.session_date = calendar.session_date(bar.datetime)
