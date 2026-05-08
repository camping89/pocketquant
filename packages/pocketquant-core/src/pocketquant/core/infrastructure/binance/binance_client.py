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
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infrastructure.binance.binance_mappers import (
    INTERVAL_TO_BINANCE,
    kline_to_bar,
    validate_symbol,
)
from pocketquant.core.infrastructure.data_provider import IDataProvider

logger = get_logger(__name__)

_KLINES_ENDPOINT = "/api/v3/klines"
_MAX_BARS_PER_CALL = 1000
_INTER_CALL_SLEEP_S = 0.1  # 100ms


class BinanceClient(IDataProvider):
    """Async REST client for Binance public klines API.

    Usage:
        client = BinanceClient(settings)
        bars = await client.fetch_ohlcv("BTCUSDT", "BINANCE", Interval.MINUTE_1, 500)
        client.close()
    """

    def __init__(
        self,
        settings: Settings,  # noqa: ARG002 — reserved for future auth/proxy config
        base_url: str = "https://api.binance.com",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)

    # ------------------------------------------------------------------
    # IDataProvider
    # ------------------------------------------------------------------

    async def fetch_ohlcv(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[Bar]:
        """Fetch n_bars OHLCV bars in ascending order.

        Paginates automatically when n_bars > 1000 (Binance limit per call).
        """
        validated_symbol = validate_symbol(symbol)
        binance_interval, bar_duration_ms = INTERVAL_TO_BINANCE[interval]

        logger.info(
            "binance.fetch_started",
            symbol=validated_symbol,
            interval=binance_interval,
            n_bars=n_bars,
        )

        all_bars: list[Bar] = []
        remaining = n_bars
        # Work backwards from now: calculate startTime for the first chunk
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        end_time_ms = now_ms

        while remaining > 0:
            chunk_limit = min(remaining, _MAX_BARS_PER_CALL)
            start_time_ms = end_time_ms - chunk_limit * bar_duration_ms

            params: dict[str, Any] = {
                "symbol": validated_symbol,
                "interval": binance_interval,
                "startTime": start_time_ms,
                "endTime": end_time_ms - 1,  # exclusive upper bound
                "limit": chunk_limit,
            }

            klines = await self._fetch_klines(params)
            if not klines:
                break

            chunk_bars = [
                kline_to_bar(k, validated_symbol, exchange, interval) for k in klines
            ]
            all_bars = chunk_bars + all_bars  # prepend so result stays ascending
            remaining -= len(klines)
            end_time_ms = start_time_ms  # slide window back

            if len(klines) < chunk_limit:
                # No more historical data available
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
        exchange: str | None = None,
    ) -> list[dict]:
        """Stub — Binance symbol search not required for current use cases."""
        return []

    async def close(self) -> None:
        """Close the underlying httpx async client."""
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
