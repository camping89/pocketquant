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


# A market that never closes can cascade its daily bar across UTC midnight, where
# its day begins. A session market's vendor builds the daily bar from its own
# session, so a cascaded one need not match the vendor's chart; those come from the
# provider.
def cascade_tfs(calendar: ITradingCalendarPort) -> list[Interval]:
    if calendar.calendar_id == CALENDAR_CRYPTO_24_7:
        return CASCADE_TFS
    return _INTRADAY_CASCADE_TFS


def tf_seconds(tf: Interval) -> int:
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


# A bucket overlaps the range when it starts before range_end and ends after
# range_start. So a bucket that closes inside the range is re-aggregated once with
# its complete 1m source even when its start is older than range_start; otherwise
# 4h and 1d freeze, because sync_1m looks back only 100 minutes. Each step goes
# through calendar.bar_start rather than a fixed number of seconds, which keeps the
# walk correct across a session gap and a DST change.
def compute_boundaries(
    tf: Interval,
    range_start: datetime,
    range_end: datetime,
    calendar: ITradingCalendarPort,
) -> list[datetime]:
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


# Higher timeframes are derived from stored 1m bars, not fetched, so the output is
# deterministic and a re-run gives the same upserts. A partial bucket is logged and
# still persisted.
async def cascade_for_symbol(
    symbol: str,
    lookback_minutes: int,
    bar_repo: BarRepository,
    calendar: ITradingCalendarPort,
) -> dict[Interval, int]:
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
