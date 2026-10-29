from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval

_SESSION_KEYED = frozenset({Interval.DAY_1, Interval.WEEK_1})


# Every path that writes provider bars stamps them here, so calendar_id and
# session_date do not depend on which job wrote the bar. Intraday bars get no
# session day: the UTC date is the wrong day for a session that opens the evening
# before.
def stamp_calendar(records: list[Bar], interval: Interval, calendar: ITradingCalendarPort) -> None:
    session_keyed = interval in _SESSION_KEYED
    for bar in records:
        bar.calendar_id = calendar.calendar_id
        if session_keyed and bar.datetime is not None:
            bar.session_date = calendar.session_date(bar.datetime)
