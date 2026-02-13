"""Handler for running optimization."""

from typing import TYPE_CHECKING

from src.common.constants import COLLECTION_OPTIMIZATION_RUNS
from src.common.database import Database
from src.common.mediator import Handler
from src.common.messaging import EventBus
from src.features.backtesting.base.models.optimization_config import OptimizationConfig
from src.features.backtesting.base.models.optimization_result import OptimizationResult
from src.features.backtesting.base.optimizer.grid_optimizer import GridOptimizer
from src.features.backtesting.optimize.command import RunOptimizationCommand

if TYPE_CHECKING:
    from src.features.strategy.base import StrategyEngine


class RunOptimizationHandler(Handler[RunOptimizationCommand, OptimizationResult]):
    """Handle RunOptimizationCommand - execute grid optimization."""

    def __init__(
        self,
        event_bus: EventBus,
        strategy_engine: StrategyEngine,
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
