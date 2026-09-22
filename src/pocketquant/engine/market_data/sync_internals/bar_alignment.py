from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.bar.services.bar_builder_domain_service import is_bar_aligned
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval


def has_aligned_bar(
    records: list[Bar], interval: Interval, calendar: ITradingCalendarPort
) -> bool:
    return any(
        b.datetime is not None and is_bar_aligned(b.datetime, interval, calendar) for b in records
    )
