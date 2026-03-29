import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import Settings
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infrastructure.tradingview.base import IDataProvider
from tvDatafeed import Interval as TVInterval
from tvDatafeed import TvDatafeed

logger = get_logger(__name__)

# Maps domain Interval enum to TvDatafeed interval attribute names
INTERVAL_TO_TVDATAFEED = {
    Interval.MINUTE_1: "in_1_minute",
    Interval.MINUTE_3: "in_3_minute",
    Interval.MINUTE_5: "in_5_minute",
    Interval.MINUTE_15: "in_15_minute",
    Interval.MINUTE_30: "in_30_minute",
    Interval.MINUTE_45: "in_45_minute",
    Interval.HOUR_1: "in_1_hour",
    Interval.HOUR_2: "in_2_hour",
    Interval.HOUR_3: "in_3_hour",
    Interval.HOUR_4: "in_4_hour",
    Interval.DAY_1: "in_daily",
    Interval.WEEK_1: "in_weekly",
    Interval.MONTH_1: "in_monthly",
}

_executor = ThreadPoolExecutor(max_workers=4)


class TradingViewClient(IDataProvider):
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: TvDatafeed | None = None
        self._semaphore = asyncio.Semaphore(2)

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
            dataframe = client.get_hist(
                symbol=symbol,
                exchange=exchange,
                interval=tv_interval,
                n_bars=min(n_bars, 5000),
            )
            return dataframe
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
    ) -> list[Bar]:
        async with self._semaphore:
            logger.info(
                "tradingview.fetch_started",
                symbol=symbol,
                exchange=exchange,
                interval=interval.value,
                n_bars=n_bars,
            )

            loop = asyncio.get_running_loop()
            dataframe = await loop.run_in_executor(
                _executor,
                self._fetch_data_sync,
                symbol,
                exchange,
                interval,
                n_bars,
            )

            if dataframe is None or dataframe.empty:
                logger.warning(
                    "tradingview.no_data",
                    symbol=symbol,
                    exchange=exchange,
                    interval=interval.value,
                )
                return []

            records: list[Bar] = []

            for row_index, row in dataframe.iterrows():
                bar_datetime = (
                    row_index if isinstance(row_index, datetime)
                    else pd.to_datetime(row_index).to_pydatetime()  # type: ignore[arg-type]
                )

                records.append(
                    Bar(
                        symbol=symbol.upper(),
                        exchange=exchange.upper(),
                        interval=interval,
                        datetime=bar_datetime,
                        open=float(row["open"]),  # type: ignore[arg-type]
                        high=float(row["high"]),  # type: ignore[arg-type]
                        low=float(row["low"]),  # type: ignore[arg-type]
                        close=float(row["close"]),  # type: ignore[arg-type]
                        volume=float(row["volume"]),  # type: ignore[arg-type]
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
