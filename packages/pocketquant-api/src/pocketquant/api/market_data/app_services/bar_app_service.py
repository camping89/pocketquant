"""BarAppService aggregates real-time ticks into bars at multiple intervals."""

import asyncio
from collections import defaultdict
from typing import Any

from pocketquant.api.market_data.app_services.quote_dto import QuoteTick
from pocketquant.core.common.constants import CACHE_KEY_BAR_CURRENT, TTL_BAR_CURRENT, build_bar_cache_key
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.bar.services.bar_builder import BarBuilder, get_bar_start
from pocketquant.core.domain.shared.value_objects import Interval
from pocketquant.core.persistence.redis import Cache
from pocketquant.core.persistence.repositories.bar_repository import BarRepository

logger = get_logger(__name__)


class BarAppService:
    """Aggregates real-time ticks into bars at multiple intervals."""

    def __init__(
        self,
        cache: Cache,
        bar_repository: BarRepository,
        event_bus: EventBus,
        intervals: list[Interval] | None = None,
    ):
        self._cache = cache
        self._bar_repo = bar_repository
        self._event_bus = event_bus
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

        domain_bar = Bar(
            symbol=bar.symbol,
            exchange=bar.exchange,
            interval=bar.interval,
            datetime=bar.bar_start,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            tick_count=bar.tick_count,
        )

        await self._bar_repo.upsert_bar(domain_bar)

        # Emit BarCompletedEvent for live strategy execution
        event = BarCompletedEvent(
            symbol=bar.symbol,
            exchange=bar.exchange,
            interval=bar.interval.value,
            bar_start=bar.bar_start,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            tick_count=bar.tick_count,
        )
        await self._event_bus.publish(event)

        cache_key = build_bar_cache_key(bar.symbol, bar.exchange, bar.interval.value)
        await self._cache.delete_pattern(f"{cache_key}:*")

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
        await self._cache.set(cache_key, bar.to_dict(), ttl=TTL_BAR_CURRENT)

    async def get_current_bar(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
    ) -> dict[str, Any] | None:
        cache_key = CACHE_KEY_BAR_CURRENT.format(
            exchange=exchange.upper(), symbol=symbol.upper(), interval=interval.value
        )
        return await self._cache.get(cache_key)

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
