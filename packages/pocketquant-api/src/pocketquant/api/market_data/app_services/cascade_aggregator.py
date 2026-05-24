"""Cascade aggregator — derives higher-tf OHLCV bars from 1m source bars.

Pure functions (aggregate_ohlcv, compute_boundaries, tf_seconds) have no DB or IO;
they are trivially unit-testable. cascade_for_symbol is the only DB-touching entry
point and receives bar_repo as a parameter (no module-level state).

Design:
- Source-of-truth: 1m bars stored in MongoDB.
- All higher tfs (5m, 15m, 1h, 4h, 1d) are derived by aggregation — not fetched from
  provider — so cascade output is deterministic and idempotent.
- UTC-aligned bucket starts: 5m at minute%5==0, 1h at hour boundary, 1d at midnight.
- Partial aggregate (< expected input count): logged as warning, still persisted.
- ``symbol`` is composite ``{code}:{exchange}`` throughout.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import SOURCE_CASCADE, Bar
from pocketquant.core.domain.shared.enums import Interval

if TYPE_CHECKING:
    from pocketquant.core.persistence.repositories.bar_repository import BarRepository

logger = get_logger(__name__)

# Higher tfs produced by cascade (1m is the source — never cascaded from itself).
CASCADE_TFS: list[Interval] = [
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
]

# Expected number of 1m bars per higher tf.
_TF_EXPECTED_BARS: dict[Interval, int] = {
    Interval.MINUTE_5: 5,
    Interval.MINUTE_15: 15,
    Interval.HOUR_1: 60,
    Interval.HOUR_4: 240,
    Interval.DAY_1: 1440,
}


def tf_seconds(tf: Interval) -> int:
    """Return the number of seconds in one bar of the given timeframe.

    Supported: 1m, 5m, 15m, 1h, 4h, 1d.
    Raises ValueError for unsupported intervals.
    """
    mapping: dict[Interval, int] = {
        Interval.MINUTE_1: 60,
        Interval.MINUTE_5: 300,
        Interval.MINUTE_15: 900,
        Interval.HOUR_1: 3_600,
        Interval.HOUR_4: 14_400,
        Interval.DAY_1: 86_400,
    }
    try:
        return mapping[tf]
    except KeyError:
        raise ValueError(f"Unsupported cascade interval: {tf!r}")


def aggregate_ohlcv(bars: list[Bar]) -> dict | None:
    """Aggregate a list of 1m bars into a single OHLCV dict.

    Pure function — no DB, no IO.
    Returns None if bars is empty.
    Always aggregates available bars even if count < expected (partial).
    Result keys: open, high, low, close, volume.
    """
    if not bars:
        return None

    # Sort by datetime ascending to ensure first/last ordering is correct.
    sorted_bars = sorted(bars, key=lambda b: b.datetime or datetime.min)

    open_ = sorted_bars[0].open
    high = max(b.high for b in sorted_bars)
    low = min(b.low for b in sorted_bars)
    close = sorted_bars[-1].close
    volume = sum(b.volume for b in sorted_bars)

    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def compute_boundaries(
    tf: Interval,
    range_start: datetime,
    range_end: datetime,
) -> list[datetime]:
    """Return UTC-aligned bucket starts whose bucket overlaps [range_start, range_end).

    A bucket [B, B + tf_seconds) overlaps the request range when both:
      - B < range_end                     (bucket starts before the range ends)
      - B + tf_seconds > range_start      (bucket ends after the range starts)

    This guarantees that a bucket which closes inside the range is re-aggregated
    once with its complete 1m source, even when the bucket *boundary* itself is
    older than range_start. Without this, larger timeframes (4h, 1d) freeze the
    moment their start instant falls outside the cron's lookback window —
    sync_jobs.sync_1m uses lookback_minutes=100, so the just-closed 4h bucket
    would otherwise never get a clean post-close aggregation pass.

    Alignment (UTC):
      5m  : minute % 5 == 0
      15m : minute % 15 == 0
      1h  : hour boundary
      4h  : hour % 4 == 0
      1d  : midnight

    Both inputs should be UTC-aware datetimes.
    """
    secs = tf_seconds(tf)

    # Align range_start DOWN to its enclosing bucket boundary so the bucket that
    # *contains* range_start (and therefore overlaps it) is included.
    epoch = range_start.timestamp()
    first_boundary_epoch = math.floor(epoch / secs) * secs
    first_boundary = datetime.fromtimestamp(first_boundary_epoch, tz=UTC)

    boundaries: list[datetime] = []
    current = first_boundary
    while current < range_end:
        boundaries.append(current)
        current = current + timedelta(seconds=secs)

    return boundaries


async def cascade_for_symbol(
    symbol: str,
    lookback_minutes: int,
    bar_repo: BarRepository,
) -> dict[Interval, int]:
    """Aggregate 1m bars from MongoDB into higher-tf bars and upsert them.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).

    For each tf in CASCADE_TFS:
      1. Determine UTC-aligned bucket boundaries within [now - lookback_minutes, now].
      2. For each bucket: query 1m bars in [boundary, boundary + tf_seconds).
      3. Aggregate OHLCV.
      4. Upsert Bar with interval=tf into MongoDB.

    Returns dict mapping each cascaded interval to the number of bars persisted.
    Idempotent: re-running with the same input bars produces the same upserts.
    """
    now = datetime.now(UTC)
    range_start = now - timedelta(minutes=lookback_minutes)

    sym = symbol.upper()

    persisted_per_tf: dict[Interval, int] = {}

    for tf in CASCADE_TFS:
        boundaries = compute_boundaries(tf, range_start, now)
        tf_secs = tf_seconds(tf)
        expected_count = _TF_EXPECTED_BARS.get(tf, 0)
        upserted = 0

        for boundary in boundaries:
            bucket_end = boundary + timedelta(seconds=tf_secs)

            # Query 1m source bars for this bucket window (inclusive start, exclusive end).
            source_bars = await bar_repo.find(
                symbol=sym,
                interval=Interval.MINUTE_1,
                start_date=boundary,
                end_date=bucket_end - timedelta(seconds=1),
                limit=expected_count + 5,  # small headroom for alignment edge bars
            )

            if not source_bars:
                continue

            actual_count = len(source_bars)
            if actual_count < expected_count:
                logger.warning(
                    "cascade.partial_aggregate",
                    symbol=sym,
                    tf=tf.value,
                    boundary=boundary.isoformat(),
                    expected=expected_count,
                    actual=actual_count,
                    missing=expected_count - actual_count,
                )

            ohlcv = aggregate_ohlcv(source_bars)
            if ohlcv is None:
                continue

            bar = Bar(
                symbol=sym,
                interval=tf,
                datetime=boundary,
                open=ohlcv["open"],
                high=ohlcv["high"],
                low=ohlcv["low"],
                close=ohlcv["close"],
                volume=ohlcv["volume"],
            )

            try:
                await bar_repo.upsert_bar(bar, source=SOURCE_CASCADE)
                upserted += 1
            except Exception:
                logger.error(
                    "cascade.upsert_failed",
                    symbol=sym,
                    tf=tf.value,
                    boundary=boundary.isoformat(),
                    exc_info=True,
                )

        persisted_per_tf[tf] = upserted
        if upserted:
            logger.info(
                "cascade.completed_tf",
                symbol=sym,
                tf=tf.value,
                buckets=len(boundaries),
                upserted=upserted,
                source=SOURCE_CASCADE,
            )

    return persisted_per_tf
