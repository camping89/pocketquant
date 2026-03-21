"""Backtest runner - orchestrates single backtest execution with broker and strategy."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pocketquant.backtest.engine.historical_replay_app_service import (
    HistoricalReplayAppService,
)
from pocketquant.backtest.optimization.models.backtest_config import BacktestConfig
from pocketquant.backtest.domain import BacktestResult
from pocketquant.backtest.engine.result_collector import BacktestResultCollector
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.value_objects import Interval
from pocketquant.core.infrastructure.brokers.paper.paper_broker import PaperBroker
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.persistence.repositories.bar_repository import BarRepository

if TYPE_CHECKING:
    from pocketquant.trading.app_services.strategy_app_service import StrategyAppService

logger = get_logger(__name__)


class BacktestAppService:
    """Orchestrates a single backtest run with metrics collection and persistence.

    Responsibilities:
    - Reset broker state before run
    - Set up result collector for metrics tracking
    - Load OHLCV data from MongoDB
    - Set current price on broker before each bar
    - Execute replay through HistoricalReplayAppService
    - Calculate metrics and persist results
    - Clean up simulation time after run

    Usage:
        runner = BacktestAppService(event_bus, strategy_engine, paper_broker)
        result = await runner.run(config)
    """

    def __init__(
        self,
        event_bus: EventBus,
        strategy_engine: StrategyAppService,
        broker: PaperBroker,
        backtest_repository: BacktestRepository,
        bar_repository: BarRepository,
        persist_results: bool = True,
    ) -> None:
        self._event_bus = event_bus
        self._strategy_engine = strategy_engine
        self._broker = broker
        self._backtest_repo = backtest_repository
        self._bar_repo = bar_repository
        self._replay_engine = HistoricalReplayAppService(event_bus)
        self._persist_results = persist_results

    async def run(self, config: BacktestConfig) -> BacktestResult:
        """Execute a single backtest run with full metrics collection.

        Args:
            config: Backtest configuration with strategy, symbol, date range.

        Returns:
            BacktestResult with metrics, equity curve, and trade history.
        """
        run_id = generate_id_str()
        started_at = datetime.now(UTC)

        logger.info(
            "backtest_starting",
            run_id=run_id,
            strategy_id=config.strategy_id,
            symbol=config.symbol,
            start_date=config.start_date.isoformat(),
            end_date=config.end_date.isoformat(),
        )

        # Create result collector
        collector = BacktestResultCollector(config, config.initial_capital)

        try:
            # Reset broker to initial state
            self._broker.reset()

            # Configure broker slippage from config
            self._broker.slippage = config.slippage_percent

            # Subscribe collector to broker fills
            await self._broker.subscribe_order_updates(collector.on_fill)

            # Load OHLCV bars from MongoDB
            bars = self._load_bars(config)

            # Create bar wrapper that sets price before yielding
            bars_with_price = self._wrap_bars_with_price_update(config, bars)

            # Execute replay
            replay_stats = await self._replay_engine.replay(config, bars_with_price)

            completed_at = datetime.now(UTC)

            # Finalize and calculate metrics
            result = collector.finalize(
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                status="completed",
            )

            logger.info(
                "backtest_completed",
                run_id=run_id,
                bars=replay_stats.bars_processed,
                trades=result.metrics.total_trades,
                sharpe=round(result.metrics.sharpe_ratio, 2),
                return_pct=round(result.metrics.total_return * 100, 2),
            )

            # Persist results if enabled
            if self._persist_results:
                await self._backtest_repo.save(result)

            return result

        except Exception as e:
            completed_at = datetime.now(UTC)
            logger.error("backtest_failed", run_id=run_id, error=str(e))

            # Create failed result with error details (validated requirement)
            result = collector.finalize(
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                status="failed",
                error_message=str(e),
            )

            # Persist failed result for debugging audit trail (validated requirement)
            if self._persist_results:
                await self._backtest_repo.save(result)

            return result

        finally:
            # Always clean up
            await self._broker.unsubscribe_order_updates()
            clear_simulation_time()

    async def _load_bars(self, config: BacktestConfig) -> AsyncIterator[Bar]:
        """Load OHLCV bars from MongoDB for the configured date range."""
        start_datetime = datetime.combine(config.start_date, datetime.min.time())
        end_datetime = datetime.combine(config.end_date, datetime.max.time())

        async for bar in self._bar_repo.stream(
            config.symbol, config.exchange, Interval(config.interval), start_datetime, end_datetime
        ):
            yield bar

    async def _wrap_bars_with_price_update(
        self, config: BacktestConfig, bars: AsyncIterator[Bar]
    ) -> AsyncIterator[Bar]:
        """Wrap bar iterator to set broker price before each bar.

        This ensures market orders fill at bar close price.
        """
        async for bar in bars:
            self._broker.set_current_price(config.symbol, bar.close)
            yield bar
