from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.calendars.exness_session_calendar_adapter import exness_bar_start
from pocketquant.core.infra.exness.exness_client import ExnessClient, max_candles
from pocketquant.core.infra.exness.exness_mappers import (
    INTERVAL_TO_EXNESS,
    candle_to_bar,
    instrument_name,
)

logger = get_logger(__name__)

_SECOND = timedelta(seconds=1)


class ExnessAdapter(IDataProviderPort):
    def __init__(self, client: ExnessClient) -> None:
        self._client = client

    # ExnessClient retries a rate limit; anything it still raises propagates, so the sync
    # reports an error and the next scheduled run fetches again.
    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[Bar]:
        name = instrument_name(symbol)
        if name is None:
            logger.warning("exness.unknown_instrument", symbol=symbol)
            return []
        page = max_candles(await self._client.limits())
        cutoff = exness_bar_start(datetime.now(UTC), interval)
        # ``from`` is inclusive, so each page ends one second before the bar in
        # progress, then before the oldest bar already fetched: no candle is
        # requested twice or dropped after counting.
        cursor = cutoff - _SECOND
        bars: list[Bar] = []
        remaining = n_bars
        while remaining > 0:
            count = min(remaining, page)
            body = await self._client.call(
                "getCandleHistory",
                params={
                    "instrument": name,
                    "timeframe": INTERVAL_TO_EXNESS[interval],
                    "price_type": "bid",
                    "from": cursor.isoformat(),
                    "count": -count,
                },
            )
            candles = body.get("candles", [])
            chunk = [candle_to_bar(c, symbol, interval) for c in candles]
            bars = [b for b in chunk if b.datetime is not None and b.datetime < cutoff] + bars
            remaining -= len(candles)
            if len(candles) < count:
                break
            cursor = min(b.datetime for b in chunk if b.datetime) - _SECOND
        logger.debug("exness.fetch_completed", symbol=symbol, bars_fetched=len(bars))
        return bars[-n_bars:] if n_bars > 0 else []

    async def search_symbols(self, query: str) -> list[dict]:
        return []

    # No-op: the client's lifetime belongs to DI.
    async def close(self) -> None: ...
