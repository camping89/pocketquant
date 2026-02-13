"""BarManager aggregates real-time ticks into OHLCV bars at multiple intervals."""

import asyncio
from collections import defaultdict
from typing import Any

from src.common.cache import Cache
from src.common.constants import (
    CACHE_KEY_BAR_CURRENT,
    COLLECTION_OHLCV,
    TTL_BAR_CURRENT,
)
from src.common.database import Database
from src.common.logging import get_logger
from src.features.market_data.base.managers.bar_builder import BarBuilder, get_bar_start
from src.features.market_data.base.models.ohlcv import OHLCV, Interval
from src.features.market_data.base.models.quote import QuoteTick

logger = get_logger(__name__)


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
        bar_start = get_bar_start(tick.timestamp, interval)

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
            _id=None,
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
            for _symbol_key, intervals in self._bars.items():
                for _interval, bar in intervals.items():
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
