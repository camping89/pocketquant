"""Bar filter helpers — split fetched records into keep/drop sets.

Two concerns:

- Existence filter (DB-aware): drop bars older than `latest - 3 intervals` to
  avoid re-inserting bars we already have. Insert pipeline handles dedupe via
  unique index, but pre-filtering cuts wire/log noise.
- Misalignment filter (pure): drop bars whose timestamps don't sit on the
  interval grid (provider sometimes returns the in-progress open bar).
"""

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.bar.services.bar_builder import filter_aligned_bars
from pocketquant.core.domain.shared.value_objects import Interval
from pocketquant.core.persistence.repositories.bar_repository import BarRepository

logger = get_logger(__name__)

_OVERLAP_BUFFER = 3


async def filter_new_bars(
    records: list[Bar],
    symbol: str,
    exchange: str,
    interval: Interval,
    bar_repo: BarRepository,
) -> list[Bar]:
    """Keep only bars from `latest - 3 intervals` onwards.

    On first sync (no existing data), returns records unchanged. The 3-bar
    overlap ensures boundary bars aren't missed; insert_many(ordered=False)
    skips duplicates via unique index.
    """
    latest = await bar_repo.get_latest(symbol, exchange, interval)
    if not latest or not latest.datetime:
        return records

    cutoff_bars = sorted(
        [r for r in records if r.datetime and r.datetime <= latest.datetime],
        key=lambda b: b.datetime,  # type: ignore[arg-type, return-value]
    )
    if len(cutoff_bars) > _OVERLAP_BUFFER:
        cutoff_dt = cutoff_bars[-_OVERLAP_BUFFER].datetime
    else:
        cutoff_dt = cutoff_bars[0].datetime if cutoff_bars else latest.datetime

    filtered = [r for r in records if r.datetime and r.datetime >= cutoff_dt]
    skipped = len(records) - len(filtered)
    if skipped > 0:
        logger.info(
            "market_data.sync.filtered_existing",
            kept=len(filtered),
            skipped=skipped,
            cutoff=str(cutoff_dt),
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
