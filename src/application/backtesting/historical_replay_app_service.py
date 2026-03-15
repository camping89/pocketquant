"""Historical replay engine for backtesting - emits BarCompletedEvent from OHLCV data."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter

from src.application.backtesting.models.backtest_config import BacktestConfig
from src.common.logging import get_logger
from src.common.messaging import EventBus
from src.common.time.simulation import set_simulation_time
from src.domain.bar import BarCompletedEvent
from src.domain.bar.entities import Bar

logger = get_logger(__name__)


@dataclass
class ReplayStats:
    """Statistics from a replay run."""

    bars_processed: int
    duration_seconds: float
    bars_per_second: float
    first_bar_time: datetime | None
    last_bar_time: datetime | None


class HistoricalReplayAppService:
    """Replays historical OHLCV bars as BarCompletedEvent for backtesting.

    Features:
    - Emits BarCompletedEvent for each bar in timestamp order
    - Sets simulation time before each event emission
    - Supports configurable replay speed (0 = max, 1 = real-time)
    - Yields to event loop periodically to prevent blocking
    """

    # Yield to event loop every N bars to prevent blocking
    YIELD_INTERVAL = 100

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def replay(
        self,
        config: BacktestConfig,
        bars: AsyncIterator[Bar],
    ) -> ReplayStats:
        """Replay bars as events, setting simulation time for each.

        Args:
            config: Backtest configuration with replay_speed.
            bars: Async iterator of OHLCV bars (must be sorted by datetime ASC).

        Returns:
            ReplayStats with processing metrics.
        """
        start_time = perf_counter()
        bars_processed = 0
        first_bar_time: datetime | None = None
        last_bar_time: datetime | None = None
        prev_bar_time: datetime | None = None

        async for bar in bars:
            # Track timing
            bar_time = bar.datetime
            if first_bar_time is None:
                first_bar_time = bar_time
            last_bar_time = bar_time

            # Set simulation time BEFORE emitting event
            set_simulation_time(bar_time)

            # Create and emit BarCompletedEvent
            event = BarCompletedEvent(
                symbol=bar.symbol,
                exchange=bar.exchange,
                interval=config.interval,
                bar_start=bar_time,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            await self._event_bus.publish(event)

            bars_processed += 1

            # Handle replay speed delay
            if config.replay_speed > 0 and prev_bar_time is not None:
                real_interval = (bar_time - prev_bar_time).total_seconds()
                delay = real_interval / config.replay_speed
                if delay > 0:
                    await asyncio.sleep(delay)

            prev_bar_time = bar_time

            # Yield to event loop periodically for responsiveness
            if bars_processed % self.YIELD_INTERVAL == 0:
                await asyncio.sleep(0)

        duration = perf_counter() - start_time
        bars_per_second = bars_processed / duration if duration > 0 else 0

        logger.info(
            "replay_completed",
            bars=bars_processed,
            duration_sec=round(duration, 2),
            bars_per_sec=round(bars_per_second, 0),
        )

        return ReplayStats(
            bars_processed=bars_processed,
            duration_seconds=duration,
            bars_per_second=bars_per_second,
            first_bar_time=first_bar_time,
            last_bar_time=last_bar_time,
        )
