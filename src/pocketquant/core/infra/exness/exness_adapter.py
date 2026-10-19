"""Exness REST data provider — implements IDataProviderPort over native bid candles.

Pages backwards from now by the published ``max_candles_per_request``. The
in-progress candle is dropped on the Exness bar grid: the UTC grid, with weeks
opening on Sunday. A rate limit is retried inside ``ExnessClient``; anything it
still raises propagates, so the sync reports an error and the next scheduled run
fetches again.
"""

from __future__ import annotations

from datetime import UTC, datetime

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


class ExnessAdapter(IDataProviderPort):
    """Bid OHLCV history for the ``:EXNESS`` symbols."""

    def __init__(self, client: ExnessClient) -> None:
        self._client = client

    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[Bar]:
        """Closed bars, ascending, at most ``n_bars``."""
        name = instrument_name(symbol)
        if name is None:
            logger.warning("exness.unknown_instrument", symbol=symbol)
            return []
        page = max_candles(await self._client.limits())
        now = datetime.now(UTC)
        cutoff = exness_bar_start(now, interval)
        cursor = now.replace(microsecond=0).isoformat()
        bars: list[Bar] = []
        seen: set[datetime] = set()
        remaining = n_bars
        while remaining > 0:
            count = min(remaining, page)
            body = await self._client.call(
                "getCandleHistory",
                params={
                    "instrument": name,
                    "timeframe": INTERVAL_TO_EXNESS[interval],
                    "price_type": "bid",
                    "from": cursor,
                    "count": -count,
                },
            )
            candles = body.get("candles", [])
            chunk = [candle_to_bar(c, symbol, interval) for c in candles]
            closed = [b for b in chunk if b.datetime is not None and b.datetime < cutoff]
            fresh = [b for b in closed if b.datetime not in seen]
            seen.update(b.datetime for b in fresh if b.datetime is not None)
            bars = fresh + bars
            remaining -= count
            if len(candles) < count:
                break
            cursor = min(b.datetime for b in chunk if b.datetime).isoformat()
        logger.debug("exness.fetch_completed", symbol=symbol, bars_fetched=len(bars))
        return bars[-n_bars:] if n_bars > 0 else []

    async def search_symbols(self, query: str) -> list[dict]:
        return []

    async def close(self) -> None:
        """No-op: the client's lifetime belongs to DI."""
