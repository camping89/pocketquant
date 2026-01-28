import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from src.common.cache import Cache
from src.common.constants import (
    CACHE_KEY_BAR_CURRENT,
    COLLECTION_OHLCV,
    TTL_BAR_CURRENT,
)
from src.common.database import Database
from src.common.logging import get_logger
from src.features.market_data.models.ohlcv import OHLCV, Interval
from src.features.market_data.models.quote import AggregatedBar, QuoteTick

logger = get_logger(__name__)

INTERVAL_SECONDS = {
    Interval.MINUTE_1: 60,
    Interval.MINUTE_3: 180,
    Interval.MINUTE_5: 300,
    Interval.MINUTE_15: 900,
    Interval.MINUTE_30: 1800,
    Interval.MINUTE_45: 2700,
    Interval.HOUR_1: 3600,
    Interval.HOUR_2: 7200,
    Interval.HOUR_3: 10800,
    Interval.HOUR_4: 14400,
    Interval.DAY_1: 86400,
}


class BarBuilder:
    def __init__(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        bar_start: datetime,
    ):
        self.symbol = symbol
        self.exchange = exchange
        self.interval = interval
        self.bar_start = bar_start
        self.bar_end = bar_start + timedelta(seconds=INTERVAL_SECONDS[interval])

        self.open: float | None = None
        self.high: float | None = None
        self.low: float | None = None
        self.close: float | None = None
        self.volume: float = 0.0
        self.tick_count: int = 0

    def add_tick(self, tick: QuoteTick) -> bool:
        if tick.timestamp < self.bar_start or tick.timestamp >= self.bar_end:
            return False

        price = tick.price

        if self.open is None:
            self.open = price

        if self.high is None or price > self.high:
            self.high = price

        if self.low is None or price < self.low:
            self.low = price

        self.close = price

        if tick.volume:
            self.volume += tick.volume

        self.tick_count += 1

        return True

    def is_complete(self, current_time: datetime) -> bool:
        return current_time >= self.bar_end

    def is_empty(self) -> bool:
        return self.tick_count == 0

    def to_aggregated_bar(self) -> AggregatedBar | None:
        if self.is_empty():
            return None

        return AggregatedBar(
            symbol=self.symbol,
            exchange=self.exchange,
            interval=self.interval.value,
            bar_start=self.bar_start,
            bar_end=self.bar_end,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            tick_count=self.tick_count,
        )

    def to_cache_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "interval": self.interval.value,
            "bar_start": self.bar_start.isoformat(),
            "bar_end": self.bar_end.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_count": self.tick_count,
        }


def _get_bar_start(timestamp: datetime, interval: Interval) -> datetime:
    seconds = INTERVAL_SECONDS[interval]

    if interval == Interval.DAY_1:
        return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)

    epoch = datetime(1970, 1, 1)
    total_seconds = (timestamp - epoch).total_seconds()
    aligned_seconds = (total_seconds // seconds) * seconds

    return epoch + timedelta(seconds=aligned_seconds)


class BarManager:
    """Aggregates real-time ticks into OHLCV bars at multiple intervals."""

    def __init__(self, intervals: list[Interval] | None = None):
        self._intervals = intervals or [
            Interval.MINUTE_1,
            Interval.MINUTE_5,
            Interval.HOUR_1,
            Interval.DAY_1,
        ]

        self._bars: dict[str, dict[Interval, BarBuilder]] = defaultdict(dict)

        self._lock = asyncio.Lock()

    async def add_tick(self, tick: QuoteTick) -> None:
        symbol_key = f"{tick.exchange}:{tick.symbol}".upper()

        async with self._lock:
            for interval in self._intervals:
                await self._process_tick_for_interval(tick, symbol_key, interval)

    async def _process_tick_for_interval(
        self,
        tick: QuoteTick,
        symbol_key: str,
        interval: Interval,
    ) -> None:
        current_bar = self._bars[symbol_key].get(interval)
        bar_start = _get_bar_start(tick.timestamp, interval)

        if current_bar is None:
            current_bar = BarBuilder(
                symbol=tick.symbol,
                exchange=tick.exchange,
                interval=interval,
                bar_start=bar_start,
            )
            self._bars[symbol_key][interval] = current_bar

        elif current_bar.is_complete(tick.timestamp):
            await self._save_completed_bar(current_bar)

            current_bar = BarBuilder(
                symbol=tick.symbol,
                exchange=tick.exchange,
                interval=interval,
                bar_start=bar_start,
            )
            self._bars[symbol_key][interval] = current_bar

        current_bar.add_tick(tick)
        await self._cache_current_bar(symbol_key, interval, current_bar)

    async def _save_completed_bar(self, bar: BarBuilder) -> None:
        if bar.is_empty():
            return

        aggregated = bar.to_aggregated_bar()
        if aggregated is None:
            return

        ohlcv = OHLCV(
            symbol=aggregated.symbol,
            exchange=aggregated.exchange,
            interval=Interval(aggregated.interval),
            datetime=aggregated.bar_start,
            open=aggregated.open,
            high=aggregated.high,
            low=aggregated.low,
            close=aggregated.close,
            volume=aggregated.volume,
        )

        collection = Database.get_collection(COLLECTION_OHLCV)
        doc = ohlcv.to_mongo()
        created_at = doc.pop("created_at", None)

        update_ops: dict = {"$set": doc}
        if created_at:
            update_ops["$setOnInsert"] = {"created_at": created_at}

        await collection.update_one(
            {
                "symbol": doc["symbol"],
                "exchange": doc["exchange"],
                "interval": doc["interval"],
                "datetime": doc["datetime"],
            },
            update_ops,
            upsert=True,
        )

        logger.info(
            "bar_manager.bar_saved",
            symbol=aggregated.symbol,
            exchange=aggregated.exchange,
            interval=aggregated.interval,
            bar_start=aggregated.bar_start.isoformat(),
            tick_count=aggregated.tick_count,
        )

    async def _cache_current_bar(
        self,
        symbol_key: str,
        interval: Interval,
        bar: BarBuilder,
    ) -> None:
        exchange, symbol = symbol_key.split(":", 1)
        cache_key = CACHE_KEY_BAR_CURRENT.format(
            exchange=exchange, symbol=symbol, interval=interval.value
        )
        await Cache.set(cache_key, bar.to_cache_dict(), ttl=TTL_BAR_CURRENT)

    async def get_current_bar(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
    ) -> dict[str, Any] | None:
        cache_key = CACHE_KEY_BAR_CURRENT.format(
            exchange=exchange.upper(), symbol=symbol.upper(), interval=interval.value
        )
        return await Cache.get(cache_key)

    async def flush_all_bars(self) -> int:
        saved_count = 0

        async with self._lock:
            for symbol_key, intervals in self._bars.items():
                for interval, bar in intervals.items():
                    if not bar.is_empty():
                        await self._save_completed_bar(bar)
                        saved_count += 1

            self._bars.clear()

        logger.info("bar_manager.bars_flushed", saved_count=saved_count)
        return saved_count

    @property
    def active_symbols(self) -> list[str]:
        return list(self._bars.keys())

    @property
    def intervals(self) -> list[Interval]:
        return self._intervals
