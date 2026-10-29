import asyncio
import time

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.engine.market_data.sync_internals.bar_alignment import has_aligned_bar

logger = get_logger(__name__)

# Retry policy: aggressive. The sync_1m cron offset (sync_jobs.py) avoids the
# bar-close race, so retry only handles residual provider hiccups.
# Promote to Settings only when (a) ops needs runtime tuning
# during a live incident, or (b) a second provider with different latency
# profile is added.
_BACKOFF_SECONDS = (0, 3, 8)
_TIME_BUDGET_SECONDS = 15


# At the exact bar close the provider may return [] or the in-progress bar; a brief
# retry recovers without breaking cron alignment. Returns the last attempt's raw
# records; the caller still runs the full filter pipeline.
async def fetch_with_retry(
    provider: IDataProviderPort,
    symbol: str,
    interval: Interval,
    n_bars: int,
    calendar: ITradingCalendarPort,
) -> tuple[list[Bar], int]:
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

        if records and has_aligned_bar(records, interval, calendar):
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
