"""Bar filter helpers — split fetched records into keep/drop sets.

Two concerns:

- Existence filter (DB-aware): drop only bars whose datetime already exists
  in DB for (symbol, interval). Lets non-contiguous gaps fill on
  next sync. Insert pipeline still handles dedup via unique index as safety
  net, but pre-filtering cuts wire/log noise.
- Misalignment filter (pure): drop bars whose timestamps don't sit on the
  interval grid (provider sometimes returns the in-progress open bar).
"""

from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time import coerce_utc
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.bar.services.bar_builder import filter_aligned_bars
from pocketquant.core.domain.shared.value_objects import Interval
from pocketquant.core.persistence.repositories.bar_repository import BarRepository

logger = get_logger(__name__)


async def filter_new_bars(
    records: list[Bar],
    symbol: str,
    interval: Interval,
    bar_repo: BarRepository,
) -> list[Bar]:
    """Drop records whose datetime already exists in DB for this key.

    ``symbol`` is composite ``{code}:{exchange}``.

    Queries existing datetimes within [min(records.dt), max(records.dt)] via
    indexed range scan and excludes them. Bars with `datetime=None` pass through
    (drop_misaligned_bars handles them). Empty input or all-None datetimes →
    returns input unchanged.

    Correctly handles non-contiguous DB state: scattered holes get filled,
    not assumed-already-present like the prior latest-cutoff heuristic.
    """
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
    # Mongo client is not tz_aware; raw projection returns naive datetimes.
    # Coerce both sides to tz-aware UTC for set membership equivalence.
    existing_set = {coerce_utc(d["datetime"]) for d in existing_docs}

    filtered = [
        r for r in records if r.datetime is None or coerce_utc(r.datetime) not in existing_set
    ]
    skipped = len(records) - len(filtered)
    if skipped > 0:
        logger.info(
            "market_data.sync.filtered_existing",
            kept=len(filtered),
            skipped=skipped,
            existing_count=len(existing_set),
        )
    return filtered


def drop_misaligned_bars(records: list[Bar], interval: Interval) -> list[Bar]:
    """Drop bars whose timestamps don't align to the interval grid."""
    aligned, misaligned = filter_aligned_bars(records, interval)
    if misaligned:
        logger.warning(
            "market_data.sync.misaligned_bars_dropped",
            count=len(misaligned),
            interval=interval.value,
            sample_times=[str(b.datetime) for b in misaligned[:3]],
        )
    return aligned
