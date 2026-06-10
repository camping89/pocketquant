"""Binance REST data provider — implements IDataProvider via /api/v3/klines.

Rate limits: 2 weight/call, 1200 weight/min budget.
Inter-call sleep: 100ms. On HTTP 429: log + raise (caller handles backoff).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import Settings
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.interfaces import IDataProvider
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.market_data.binance.binance_mappers import (
    INTERVAL_TO_BINANCE,
    kline_to_bar,
    validate_symbol,
)

logger = get_logger(__name__)

_KLINES_ENDPOINT = "/api/v3/klines"
_MAX_BARS_PER_CALL = 1000
_INTER_CALL_SLEEP_S = 0.1  # 100ms


class BinanceClient(IDataProvider):
    """Async REST client for Binance public klines API.

    Usage:
        client = BinanceClient(settings)
        bars = await client.fetch_ohlcv("BTCUSDT:BINANCE", Interval.MINUTE_1, 500)
        client.close()
    """

    def __init__(
        self,
        settings: Settings,  # noqa: ARG002 — reserved for future auth/proxy config
        base_url: str = "https://api.binance.com",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)

    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[Bar]:
        """Fetch n_bars OHLCV bars in ascending order.

        ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
        Paginates automatically when n_bars > 1000 (Binance limit per call).
        """
        # Extract bare code from composite symbol for Binance API (BINANCE-specific boundary)
        code = symbol.split(":")[0] if ":" in symbol else symbol
        validated_symbol = validate_symbol(code)
        binance_interval, bar_duration_ms = INTERVAL_TO_BINANCE[interval]

        logger.info(
            "binance.fetch_started",
            symbol=validated_symbol,
            interval=binance_interval,
            n_bars=n_bars,
        )

        all_bars: list[Bar] = []
        remaining = n_bars
        # Cap endTime at the last CLOSED bar boundary, excluding the in-progress bar.
        # Binance returns a kline whose openTime equals floor(now/duration)*duration with
        # only the partial data accumulated since that boundary; persisting it corrupts
        # OHLCV until the bar closes. By stopping the window at the previous boundary we
        # guarantee every returned kline is final.
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        last_closed_open_ms = (now_ms // bar_duration_ms) * bar_duration_ms
        cutoff_dt = datetime.fromtimestamp(last_closed_open_ms / 1000, tz=UTC)
        end_time_ms = last_closed_open_ms

        while remaining > 0:
            chunk_limit = min(remaining, _MAX_BARS_PER_CALL)
            start_time_ms = end_time_ms - chunk_limit * bar_duration_ms

            params: dict[str, Any] = {
                "symbol": validated_symbol,
                "interval": binance_interval,
                # endTime is inclusive on Binance; -1 ms ensures the in-progress bar
                # at last_closed_open_ms is never returned even under clock skew.
                "startTime": start_time_ms,
                "endTime": end_time_ms - 1,
                "limit": chunk_limit,
            }

            klines = await self._fetch_klines(params)
            if not klines:
                break

            chunk_bars = [kline_to_bar(k, symbol.upper(), interval) for k in klines]
            # Defense-in-depth: drop any bar whose openTime >= cutoff in case Binance
            # returns one despite endTime cap (clock skew / server-side off-by-one).
            filtered = [b for b in chunk_bars if b.datetime is not None and b.datetime < cutoff_dt]
            dropped = len(chunk_bars) - len(filtered)
            if dropped:
                logger.debug(
                    "binance.in_progress_bar_filtered",
                    symbol=validated_symbol,
                    interval=binance_interval,
                    count=dropped,
                )
            all_bars = filtered + all_bars  # prepend so result stays ascending
            remaining -= len(klines)
            end_time_ms = start_time_ms

            if len(klines) < chunk_limit:
                break

            if remaining > 0:
                await asyncio.sleep(_INTER_CALL_SLEEP_S)

        logger.info(
            "binance.fetch_completed",
            symbol=validated_symbol,
            bars_fetched=len(all_bars),
        )
        return all_bars

    async def search_symbols(
        self,
        query: str,
    ) -> list[dict]:
        """Stub — Binance symbol search not required for current use cases."""
        return []

    async def close(self) -> None:
        """Close the underlying httpx async client."""
        await self._http.aclose()

    async def _fetch_klines(self, params: dict[str, Any]) -> list[list[Any]]:
        """Execute one GET /api/v3/klines call.

        Raises httpx.HTTPStatusError on HTTP 429 (caller should backoff).
        """
        response = await self._http.get(_KLINES_ENDPOINT, params=params)

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "unknown")
            logger.warning(
                "binance.rate_limited",
                retry_after=retry_after,
                symbol=params.get("symbol"),
            )
            response.raise_for_status()  # raises HTTPStatusError

        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]
