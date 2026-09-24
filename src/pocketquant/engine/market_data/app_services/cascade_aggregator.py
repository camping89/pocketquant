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

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import SOURCE_CASCADE, Bar
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.value_objects import CALENDAR_CRYPTO_24_7

if TYPE_CHECKING:
    from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository

logger = get_logger(__name__)

# Higher tfs produced by cascade (1m is the source — never cascaded from itself).
CASCADE_TFS: list[Interval] = [
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
]

_INTRADAY_CASCADE_TFS: list[Interval] = [
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
]


def cascade_tfs(calendar: ITradingCalendarPort) -> list[Interval]:
    """Timeframes to derive from 1m bars for a symbol on ``calendar``.

    A market that never closes can have its daily bar built by cascading 1m
    across UTC midnight, because that is exactly where its day begins. A session
    market's day begins at the session open the evening before, so a cascaded
    daily bar would never match the vendor's own chart. Those come from the
    provider instead.
    """
    if calendar.calendar_id == CALENDAR_CRYPTO_24_7:
        return CASCADE_TFS
    return _INTRADAY_CASCADE_TFS


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

    sorted_bars = sorted(bars, key=lambda b: b.datetime or datetime.min.replace(tzinfo=UTC))

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
    calendar: ITradingCalendarPort,
) -> list[datetime]:
    """Return calendar-aligned bucket starts whose bucket overlaps [range_start, range_end).

    A bucket [B, B + tf_seconds) overlaps the request range when both:
      - B < range_end                     (bucket starts before the range ends)
      - B + tf_seconds > range_start      (bucket ends after the range starts)

    This guarantees that a bucket which closes inside the range is re-aggregated
    once with its complete 1m source, even when the bucket *boundary* itself is
    older than range_start. Without this, larger timeframes (4h, 1d) freeze the
    moment their start instant falls outside the cron's lookback window —
    sync_jobs.sync_1m uses lookback_minutes=100, so the just-closed 4h bucket
    would otherwise never get a clean post-close aggregation pass.

    Pure: the calendar is a parameter, never a lookup. Each step goes back
    through ``calendar.bar_start`` rather than adding a fixed number of seconds,
    which is what keeps the walk correct across a session gap and across a DST
    transition. On the 24/7 calendar that reproduces the old UTC-epoch grid
    exactly.

    Both range inputs should be UTC-aware datetimes.
    """
    secs = tf_seconds(tf)
    step = timedelta(seconds=secs)

    boundaries: list[datetime] = []
    current = calendar.bar_start(range_start, tf)
    while current < range_end:
        boundaries.append(current)
        nxt = calendar.bar_start(current + step, tf)
        if nxt <= current:
            # A calendar that maps the next instant back onto this bucket would
            # spin this loop forever inside a cron job. Step over it instead and
            # say so, rather than hanging the sync.
            logger.debug(
                "cascade.boundary_step_fallback",
                tf=tf.value,
                calendar_id=calendar.calendar_id,
                boundary=current.isoformat(),
            )
            nxt = current + step
        current = nxt

    return boundaries


async def cascade_for_symbol(
    symbol: str,
    lookback_minutes: int,
    bar_repo: BarRepository,
    calendar: ITradingCalendarPort,
) -> dict[Interval, int]:
    """Aggregate 1m bars from MongoDB into higher-tf bars and upsert them.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).

    For each tf in ``cascade_tfs(calendar)``:
      1. Determine calendar-aligned bucket boundaries within [now - lookback_minutes, now].
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

    for tf in cascade_tfs(calendar):
        boundaries = compute_boundaries(tf, range_start, now, calendar)
        tf_secs = tf_seconds(tf)
        upserted = 0

        for boundary in boundaries:
            bucket_end = boundary + timedelta(seconds=tf_secs)
            # The calendar says how many 1m bars this bucket can hold; a holiday
            # or an early close makes a session bucket legitimately shorter.
            expected_count = len(calendar.trading_minutes(boundary, bucket_end))

            source_bars = await bar_repo.find(
                symbol=sym,
                interval=Interval.MINUTE_1,
                start_date=boundary,
                end_date=bucket_end - timedelta(seconds=1),
                limit=expected_count + 5,  # small headroom for alignment edge bars
            )

            # A bucket short of 1m bars is not reported here. An open bucket is
            # still filling, a delayed feed fills closed buckets late, and a
            # thin market has minutes with no trade at all. Real gaps are the
            # daily integrity check's job (``integrity_jobs.check_integrity``),
            # which feeds ``sync_repair``.
            if not source_bars:
                continue

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
                calendar_id=calendar.calendar_id,
                session_date=calendar.session_date(boundary) if tf is Interval.DAY_1 else None,
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
            logger.debug(
                "cascade.completed_tf",
                symbol=sym,
                tf=tf.value,
                buckets=len(boundaries),
                upserted=upserted,
                source=SOURCE_CASCADE,
            )

    return persisted_per_tf
