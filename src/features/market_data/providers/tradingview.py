"""TradingView data provider using tvdatafeed library.

This provider fetches historical OHLCV data from TradingView.
Note: TradingView does not have an official API, so this uses the unofficial
tvdatafeed library which scrapes data from TradingView's WebSocket connection.

Limitations:
- Maximum 5000 bars per request
- Some symbols may require a TradingView account
- Rate limiting may apply
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
from tvDatafeed import Interval as TVInterval
from tvDatafeed import TvDatafeed

from src.common.logging import get_logger
from src.config import Settings
from src.features.market_data.models.ohlcv import (
    INTERVAL_TO_TVDATAFEED,
    Interval,
    OHLCVCreate,
)

logger = get_logger(__name__)

# Thread pool for running sync tvdatafeed in async context
_executor = ThreadPoolExecutor(max_workers=4)


class TradingViewProvider:
    """Provider for fetching market data from TradingView."""

    def __init__(self, settings: Settings):
        """Initialize TradingView provider.

        Args:
            settings: Application settings with optional TradingView credentials.
        """
        self._settings = settings
        self._client: TvDatafeed | None = None

    def _get_client(self) -> TvDatafeed:
        """Get or create TvDatafeed client.

        Returns:
            TvDatafeed client instance.
        """
        if self._client is None:
            username = self._settings.tradingview_username
            password = self._settings.tradingview_password

            if username and password:
                logger.info("tradingview_authenticated_login")
                self._client = TvDatafeed(username=username, password=password)
            else:
                logger.info("tradingview_anonymous_login")
                self._client = TvDatafeed()

        return self._client

    def _get_tv_interval(self, interval: Interval) -> TVInterval:
        """Convert our interval to tvdatafeed interval.

        Args:
            interval: Our interval enum.

        Returns:
            TvDatafeed interval enum.
        """
        interval_name = INTERVAL_TO_TVDATAFEED.get(interval)
        if interval_name is None:
            raise ValueError(f"Unsupported interval: {interval}")
        return getattr(TVInterval, interval_name)

    def _fetch_data_sync(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        n_bars: int,
    ) -> pd.DataFrame | None:
        """Synchronously fetch data from TradingView.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.
            interval: Time interval.
            n_bars: Number of bars to fetch (max 5000).

        Returns:
            DataFrame with OHLCV data or None if fetch failed.
        """
        client = self._get_client()
        tv_interval = self._get_tv_interval(interval)

        try:
            df = client.get_hist(
                symbol=symbol,
                exchange=exchange,
                interval=tv_interval,
                n_bars=min(n_bars, 5000),  # tvdatafeed max is 5000
            )
            return df
        except Exception as e:
            logger.error(
                "tradingview_fetch_error",
                symbol=symbol,
                exchange=exchange,
                interval=interval.value,
                error=str(e),
            )
            return None

    async def fetch_ohlcv(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[OHLCVCreate]:
        """Fetch OHLCV data from TradingView.

        Args:
            symbol: Trading symbol (e.g., AAPL, BTCUSD).
            exchange: Exchange name (e.g., NASDAQ, BINANCE).
            interval: Time interval for the bars.
            n_bars: Number of bars to fetch (max 5000).

        Returns:
            List of OHLCV data objects.
        """
        logger.info(
            "tradingview_fetch_start",
            symbol=symbol,
            exchange=exchange,
            interval=interval.value,
            n_bars=n_bars,
        )

        # Run sync tvdatafeed in thread pool to not block event loop
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            _executor,
            self._fetch_data_sync,
            symbol,
            exchange,
            interval,
            n_bars,
        )

        if df is None or df.empty:
            logger.warning(
                "tradingview_no_data",
                symbol=symbol,
                exchange=exchange,
                interval=interval.value,
            )
            return []

        # Convert DataFrame to list of OHLCVCreate objects
        records: list[OHLCVCreate] = []

        for idx, row in df.iterrows():
            # tvdatafeed returns datetime as index
            bar_datetime = idx if isinstance(idx, datetime) else pd.to_datetime(idx)

            records.append(
                OHLCVCreate(
                    symbol=symbol.upper(),
                    exchange=exchange.upper(),
                    interval=interval,
                    datetime=bar_datetime,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )

        logger.info(
            "tradingview_fetch_complete",
            symbol=symbol,
            exchange=exchange,
            interval=interval.value,
            record_count=len(records),
        )

        return records

    async def search_symbols(self, query: str, exchange: str | None = None) -> list[dict]:
        """Search for symbols on TradingView.

        Note: This is a basic implementation. For more advanced screening,
        consider using tradingview-screener library.

        Args:
            query: Search query.
            exchange: Optional exchange filter.

        Returns:
            List of matching symbols.
        """
        # tvdatafeed doesn't have built-in search
        # For now, return empty - can be extended with tradingview-screener
        logger.warning("symbol_search_not_implemented")
        return []

    def close(self) -> None:
        """Close the provider and cleanup resources."""
        self._client = None
        logger.info("tradingview_provider_closed")
