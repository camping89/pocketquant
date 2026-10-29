from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time import coerce_utc
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.bar.services.bar_builder_domain_service import filter_aligned_bars
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository

logger = get_logger(__name__)


# Drops only datetimes already stored, so non-contiguous holes fill on the next
# sync. The unique index still dedups inserts; this filter cuts wire and log noise.
# Bars with datetime None pass through for drop_misaligned_bars.
async def filter_new_bars(
    records: list[Bar],
    symbol: str,
    interval: Interval,
    bar_repo: BarRepository,
) -> list[Bar]:
    if not records:
        return records

    times = [r.datetime for r in records if r.datetime is not None]
    if not times:
        return records

    existing_docs = await bar_repo.find_datetimes(
        symbol,
        interval,
        start_date=min(times),
        end_date=max(times),
    )
    # The Mongo client is tz_aware=True, so raw projections already return
    # UTC-aware datetimes; coerce_utc stays as a cheap idempotent safety net.
    existing_set = {coerce_utc(d["datetime"]) for d in existing_docs}

    filtered = [
        r for r in records if r.datetime is None or coerce_utc(r.datetime) not in existing_set
    ]
    skipped = len(records) - len(filtered)
    if skipped > 0:
        logger.debug(
            "market_data.sync.filtered_existing",
            kept=len(filtered),
            skipped=skipped,
            existing_count=len(existing_set),
        )
    return filtered


# The provider sometimes returns the in-progress open bar off the interval grid.
def drop_misaligned_bars(
    records: list[Bar], interval: Interval, calendar: ITradingCalendarPort
) -> list[Bar]:
    aligned, misaligned = filter_aligned_bars(records, interval, calendar)
    if misaligned:
        logger.warning(
            "market_data.sync.misaligned_bars_dropped",
            count=len(misaligned),
            interval=interval.value,
            calendar_id=calendar.calendar_id,
            sample_times=[str(b.datetime) for b in misaligned[:3]],
        )
    return aligned
