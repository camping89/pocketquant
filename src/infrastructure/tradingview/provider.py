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
from src.infrastructure.tradingview.base import IDataProvider

logger = get_logger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


class TradingViewProvider(IDataProvider):
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: TvDatafeed | None = None

    def _get_client(self) -> TvDatafeed:
        if self._client is None:
            username = self._settings.tradingview_username
            password = self._settings.tradingview_password

            if username and password:
                logger.info("tradingview.authenticated")
                self._client = TvDatafeed(username=username, password=password)
            else:
                logger.info("tradingview.anonymous")
                self._client = TvDatafeed()

        return self._client

    def _get_tv_interval(self, interval: Interval) -> TVInterval:
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
        client = self._get_client()
        tv_interval = self._get_tv_interval(interval)

        try:
            df = client.get_hist(
                symbol=symbol,
                exchange=exchange,
                interval=tv_interval,
                n_bars=min(n_bars, 5000),
            )
            return df
        except Exception as e:
            logger.error(
                "tradingview.fetch_failed",
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
        logger.info(
            "tradingview.fetch_started",
            symbol=symbol,
            exchange=exchange,
            interval=interval.value,
            n_bars=n_bars,
        )

        loop = asyncio.get_running_loop()
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
                "tradingview.no_data",
                symbol=symbol,
                exchange=exchange,
                interval=interval.value,
            )
            return []

        records: list[OHLCVCreate] = []

        for idx, row in df.iterrows():
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
            "tradingview.fetch_completed",
            symbol=symbol,
            exchange=exchange,
            interval=interval.value,
            record_count=len(records),
        )

        return records

    async def search_symbols(self, query: str, exchange: str | None = None) -> list[dict]:
        logger.warning("tradingview.search_not_implemented")
        return []

    def close(self) -> None:
        self._client = None
        logger.info("tradingview.closed")
