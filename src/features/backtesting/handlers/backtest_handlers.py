"""CQRS handlers for backtesting commands and queries."""

from typing import TYPE_CHECKING

from src.common.constants import COLLECTION_OPTIMIZATION_RUNS
from src.common.database import Database
from src.common.mediator import Handler
from src.common.messaging import EventBus
from src.features.backtesting.engine.backtest_runner import BacktestRunner
from src.features.backtesting.handlers.backtest_commands import (
    GetBacktestQuery,
    GetOptimizationQuery,
    ListBacktestsQuery,
    RunBacktestCommand,
    RunOptimizationCommand,
)
from src.features.backtesting.models.backtest_config import BacktestConfig
from src.features.backtesting.models.backtest_result import BacktestResult
from src.features.backtesting.models.optimization_config import OptimizationConfig
from src.features.backtesting.models.optimization_result import OptimizationResult
from src.features.backtesting.optimizer.grid_optimizer import GridOptimizer
from src.features.backtesting.repository.backtest_repository import BacktestRepository
from src.infrastructure.brokers.paper.paper_broker import PaperBroker

if TYPE_CHECKING:
    from src.features.strategy.engine.strategy_engine import StrategyEngine


class RunBacktestHandler(Handler[RunBacktestCommand, BacktestResult]):
    """Handle RunBacktestCommand - execute a single backtest."""

    def __init__(
        self,
        event_bus: EventBus,
        strategy_engine: "StrategyEngine",
    ) -> None:
        self._event_bus = event_bus
        self._strategy_engine = strategy_engine

    async def handle(self, request: RunBacktestCommand) -> BacktestResult:
        """Execute backtest and return result."""
        config = BacktestConfig(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            exchange=request.exchange,
            interval=request.interval,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            slippage_bps=request.slippage_bps,
            commission_bps=request.commission_bps,
            parameters=request.parameters or {},
        )

        # Create fresh broker for this backtest
        broker = PaperBroker(
            initial_balance=request.initial_capital,
            slippage_percent=config.slippage_percent,
        )

        runner = BacktestRunner(
            event_bus=self._event_bus,
            strategy_engine=self._strategy_engine,
            broker=broker,
        )

        return await runner.run(config)


class RunOptimizationHandler(Handler[RunOptimizationCommand, OptimizationResult]):
    """Handle RunOptimizationCommand - execute grid optimization."""

    def __init__(
        self,
        event_bus: EventBus,
        strategy_engine: "StrategyEngine",
    ) -> None:
        self._event_bus = event_bus
        self._strategy_engine = strategy_engine

    async def handle(self, request: RunOptimizationCommand) -> OptimizationResult:
        """Execute optimization and return result."""
        config = OptimizationConfig(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            exchange=request.exchange,
            interval=request.interval,
            start_date=request.start_date,
            end_date=request.end_date,
            parameter_grid=request.parameter_grid,
            initial_capital=request.initial_capital,
            slippage_bps=request.slippage_bps,
            commission_bps=request.commission_bps,
            target_metric=request.target_metric,
            max_workers=request.max_workers,
        )

        optimizer = GridOptimizer(
            event_bus=self._event_bus,
            strategy_engine=self._strategy_engine,
        )

        result = await optimizer.optimize(config)

        # Persist optimization result
        await self._save_optimization_result(result)

        return result

    async def _save_optimization_result(self, result: OptimizationResult) -> None:
        """Persist optimization result to MongoDB."""
        collection = Database.get_collection(COLLECTION_OPTIMIZATION_RUNS)
        await collection.replace_one(
            {"_id": result.id}, result.to_dict(), upsert=True
        )


class GetBacktestHandler(Handler[GetBacktestQuery, BacktestResult | None]):
    """Handle GetBacktestQuery - retrieve backtest result by ID."""

    async def handle(self, request: GetBacktestQuery) -> BacktestResult | None:
        """Fetch backtest result from repository."""
        return await BacktestRepository.get(request.run_id)


class GetOptimizationHandler(Handler[GetOptimizationQuery, OptimizationResult | None]):
    """Handle GetOptimizationQuery - retrieve optimization result by ID."""

    async def handle(self, request: GetOptimizationQuery) -> OptimizationResult | None:
        """Fetch optimization result from MongoDB."""
        collection = Database.get_collection(COLLECTION_OPTIMIZATION_RUNS)
        doc = await collection.find_one({"_id": request.optimization_id})

        if not doc:
            return None

        return OptimizationResult.from_dict(doc)


class ListBacktestsHandler(Handler[ListBacktestsQuery, list[BacktestResult]]):
    """Handle ListBacktestsQuery - list backtest results for a strategy."""

    async def handle(self, request: ListBacktestsQuery) -> list[BacktestResult]:
        """Fetch backtest results from repository."""
        return await BacktestRepository.list_by_strategy(
            strategy_id=request.strategy_id,
            limit=request.limit,
            include_failed=request.include_failed,
        )
