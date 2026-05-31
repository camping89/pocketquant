"""Bounded retry around IDataProvider.fetch_ohlcv.

Provider may return [] or in-progress (misaligned) bar at exact bar-close
moment. Brief retry recovers without breaking cron alignment.

Tunables intentionally module-level constants (KISS). Promote to Settings
only when ops needs runtime tuning.
"""

import asyncio
import time

from pocketquant.api.market_data.handlers.sync.sync_one.bar_alignment import has_aligned_bar
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.market_data.interfaces import IDataProvider

logger = get_logger(__name__)

# Retry policy: aggressive. Combined with +2s cron offset (sync_jobs.py) which
# eliminates the bar-close race; retry now only handles residual Binance hiccups.
# See docs/learning/retry-tuning-aggressive-vs-conservative.md for the decision
# and trade-offs. Promote to Settings only when (a) ops needs runtime tuning
# during a live incident, or (b) a second provider with different latency
# profile is added.
_BACKOFF_SECONDS = (0, 3, 8)
_TIME_BUDGET_SECONDS = 15


async def fetch_with_retry(
    provider: IDataProvider,
    symbol: str,
    interval: Interval,
    n_bars: int,
) -> tuple[list[Bar], int]:
    """Fetch bars; retry on empty / all-misaligned response.

    ``symbol`` is composite ``{code}:{exchange}``.
    Returns (records, attempts). `records` is the LAST attempt's raw output —
    caller still runs full filter pipeline (existing + alignment).
    """
    deadline = time.monotonic() + _TIME_BUDGET_SECONDS
    records: list[Bar] = []
    attempt = 0

    for attempt, delay in enumerate(_BACKOFF_SECONDS, start=1):
        if delay:
            if time.monotonic() + delay > deadline:
                # Roll attempt back so caller sees the actual count tried.
                attempt -= 1
                break
            await asyncio.sleep(delay)

        records = await provider.fetch_ohlcv(
            symbol=symbol,
            interval=interval,
            n_bars=n_bars,
        )

        if records and has_aligned_bar(records, interval):
            if attempt > 1:
                logger.info(
                    "market_data.sync.fetch_recovered",
                    symbol=symbol,
                    interval=interval.value,
                    attempt=attempt,
                    fetched=len(records),
                )
            return records, attempt

    # All attempts exhausted — caller (anomaly_log.emit_no_progress) handles the streak.
    return records, attempt
