from collections.abc import AsyncIterator
from datetime import UTC, datetime

from pocketquant.backtest.engine.historical_replay_app_service import (
    HistoricalReplayAppService,
)
from pocketquant.backtest.engine.result_collector import BacktestResultCollector
from pocketquant.backtest.optimization.models.backtest_config import BacktestConfig
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.brokers.paper.paper_broker import PaperBroker
from pocketquant.core.infra.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository

logger = get_logger(__name__)


class BacktestAppService:
    """Orchestrates a single backtest run with metrics collection and 3-collection persistence.

    Responsibilities:
    - Reset broker state before run
    - Set up result collector for metrics tracking
    - Load OHLCV data from MongoDB
    - Set current price on broker before each bar
    - Execute replay through HistoricalReplayAppService
    - Expire any still-pending LIMITs at end of run (forward-test parity)
    - Persist 3 lists in order: orders → trades → run
    - Clean up simulation time after run
    """

    def __init__(
        self,
        event_bus: EventBus,
        broker: PaperBroker,
        backtest_repository: BacktestRepository,
        bar_repository: BarRepository,
        order_repository: BacktestOrderRepository | None = None,
        trade_repository: BacktestTradeRepository | None = None,
        persist_results: bool = True,
    ) -> None:
        self._event_bus = event_bus
        self._broker = broker
        self._backtest_repo = backtest_repository
        self._order_repo = order_repository
        self._trade_repo = trade_repository
        self._bar_repo = bar_repository
        self._replay_engine = HistoricalReplayAppService(event_bus)
        self._persist_results = persist_results

    async def run(self, config: BacktestConfig) -> BacktestResult:
        """Execute a single backtest run with full metrics collection.

        Returns the slim BacktestResult (metrics + equity_curve + open_positions);
        Orders and Trades are persisted to ``backtest_orders`` and ``backtest_trades``
        respectively and must be queried via their dedicated repositories.
        """
        run_id = generate_id_str()
        started_at = datetime.now(UTC)

        logger.info(
            "backtest_starting",
            run_id=run_id,
            strategy_code=config.strategy_code,
            symbol=config.symbol,
            start_date=config.start_date.isoformat(),
            end_date=config.end_date.isoformat(),
        )

        collector = BacktestResultCollector(config, config.initial_capital, run_id=run_id)

        try:
            self._broker.reset()
            self._broker.slippage = config.slippage_percent

            # Subscribe to BOTH channels — fills for trade-building, events for audit log.
            await self._broker.subscribe_order_updates(collector.on_fill)
            await self._broker.subscribe_order_event(collector.on_event)

            bars = self._load_bars(config)
            bars_with_price = self._wrap_bars_with_price_update(config, bars)

            replay_stats = await self._replay_engine.replay(config, bars_with_price)

            # Expire any LIMIT-like orders still pending (forward-test parity)
            expired = await self._broker.expire_pending_orders()
            if expired:
                logger.info("backtest_pending_expired", run_id=run_id, expired=expired)

            completed_at = datetime.now(UTC)

            collected = collector.finalize(
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                status="completed",
            )

            logger.info(
                "backtest_completed",
                run_id=run_id,
                bars=replay_stats.bars_processed,
                trades=collected.run.metrics.total_trades,
                orders=len(collected.orders),
                sharpe=round(collected.run.metrics.sharpe_ratio, 2),
                return_pct=round(collected.run.metrics.total_return * 100, 2),
            )

            if self._persist_results:
                # Order matters: orders → trades → run.
                if self._order_repo is not None:
                    await self._order_repo.save_many(collected.orders)
                if self._trade_repo is not None:
                    await self._trade_repo.save_many(collected.trades)
                await self._backtest_repo.save(collected.run)

            return collected.run

        except Exception as e:
            completed_at = datetime.now(UTC)
            logger.error("backtest_failed", run_id=run_id, error=str(e))

            collected = collector.finalize(
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                status="failed",
                error_message=str(e),
            )

            if self._persist_results:
                # Best-effort partial persistence for audit trail
                try:
                    if self._order_repo is not None:
                        await self._order_repo.save_many(collected.orders)
                    if self._trade_repo is not None:
                        await self._trade_repo.save_many(collected.trades)
                except Exception as persist_err:  # noqa: BLE001
                    logger.warning("backtest_partial_persist_failed", error=str(persist_err))
                await self._backtest_repo.save(collected.run)

            return collected.run

        finally:
            await self._broker.unsubscribe_order_updates()
            await self._broker.unsubscribe_order_event()
            clear_simulation_time()

    async def _load_bars(self, config: BacktestConfig) -> AsyncIterator[Bar]:
        """Load OHLCV bars from MongoDB for the configured date range."""
        start_datetime = datetime.combine(config.start_date, datetime.min.time())
        end_datetime = datetime.combine(config.end_date, datetime.max.time())

        async for bar in self._bar_repo.stream(
            config.symbol, Interval(config.interval), start_datetime, end_datetime
        ):
            yield bar

    async def _wrap_bars_with_price_update(
        self, config: BacktestConfig, bars: AsyncIterator[Bar]
    ) -> AsyncIterator[Bar]:
        """Wrap bar iterator to set broker price before each bar (market orders use bar close)."""
        async for bar in bars:
            self._broker.set_current_price(config.symbol, bar.close)
            yield bar
