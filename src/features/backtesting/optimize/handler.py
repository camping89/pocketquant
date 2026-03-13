"""Handler for running optimization."""


from src.application.backtesting.grid_optimizer import GridOptimizer
from src.application.backtesting.models.optimization_config import OptimizationConfig
from src.application.backtesting.models.optimization_result import OptimizationResult
from src.application.strategy.strategy_engine import StrategyEngine
from src.common.mediator import Handler, handles
from src.common.messaging import EventBus
from src.features.backtesting.optimize.command import RunOptimizationCommand
from src.persistence.repositories.backtest_repository import BacktestRepository
from src.persistence.repositories.ohlcv_repository import OHLCVRepository
from src.persistence.repositories.optimization_repository import OptimizationRepository


@handles(RunOptimizationCommand)
class RunOptimizationHandler(Handler[RunOptimizationCommand, OptimizationResult]):
    """Handle RunOptimizationCommand - execute grid optimization."""

    def __init__(
        self,
        event_bus: EventBus,
        strategy_engine: StrategyEngine,
        backtest_repository: BacktestRepository,
        ohlcv_repository: OHLCVRepository,
        optimization_repository: OptimizationRepository,
    ) -> None:
        self._event_bus = event_bus
        self._strategy_engine = strategy_engine
        self._backtest_repo = backtest_repository
        self._ohlcv_repo = ohlcv_repository
        self._optimization_repo = optimization_repository

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
            backtest_repository=self._backtest_repo,
            ohlcv_repository=self._ohlcv_repo,
        )

        result = await optimizer.optimize(config)

        # Persist optimization result
        await self._optimization_repo.save(result)

        return result
