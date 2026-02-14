"""BarManager aggregates real-time ticks into OHLCV bars at multiple intervals."""

import asyncio
from collections import defaultdict
from typing import Any

from src.common.cache import Cache
from src.common.constants import CACHE_KEY_BAR_CURRENT, TTL_BAR_CURRENT
from src.common.logging import get_logger
from src.domain.ohlcv.services.bar_builder import BarBuilder, get_bar_start
from src.domain.shared.value_objects import Interval
from src.persistence.repositories.ohlcv_repository import OHLCVRepository
from src.persistence.schemas.ohlcv_schema import OHLCV
from src.persistence.schemas.quote_schema import QuoteTick

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

        current_bar.add_tick(tick.price, tick.volume, tick.timestamp)
        await self._cache_current_bar(symbol_key, interval, current_bar)

    async def _save_completed_bar(self, bar: BarBuilder) -> None:
        if bar.is_empty():
            return

        if bar.open is None or bar.high is None or bar.low is None or bar.close is None:
            return

        ohlcv = OHLCV(
            _id=None,
            symbol=bar.symbol,
            exchange=bar.exchange,
            interval=bar.interval,
            datetime=bar.bar_start,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )

        await OHLCVRepository.upsert_bar(ohlcv)

        logger.info(
            "bar_manager.bar_saved",
            symbol=bar.symbol,
            exchange=bar.exchange,
            interval=bar.interval.value,
            bar_start=bar.bar_start.isoformat(),
            tick_count=bar.tick_count,
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
        await Cache.set(cache_key, bar.to_dict(), ttl=TTL_BAR_CURRENT)

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
