from pocketquant.core.domain.backtest import OptimizationResult
from pocketquant.backtest.handlers.optimize.command import RunOptimizationCommand
from pocketquant.backtest.optimization.grid_optimization_app_service import (
    GridOptimizationAppService,
)
from pocketquant.backtest.optimization.models.optimization_config import OptimizationConfig
from pocketquant.infrastructure.persistence.repositories.backtest_repository import BacktestRepository
from pocketquant.infrastructure.persistence.repositories.optimization_repository import OptimizationRepository
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.common.messaging import EventBus
from pocketquant.infrastructure.persistence.repositories.bar_repository import BarRepository


@handles(RunOptimizationCommand)
class RunOptimizationHandler(Handler[RunOptimizationCommand, OptimizationResult]):
    def __init__(
        self,
        event_bus: EventBus,
        backtest_repository: BacktestRepository,
        bar_repository: BarRepository,
        optimization_repository: OptimizationRepository,
    ) -> None:
        self._event_bus = event_bus
        self._backtest_repo = backtest_repository
        self._bar_repo = bar_repository
        self._optimization_repo = optimization_repository

    async def handle(self, request: RunOptimizationCommand) -> OptimizationResult:
        config = OptimizationConfig(
            strategy_code=request.strategy_id,
            symbol=request.symbol,
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

        optimizer = GridOptimizationAppService(
            event_bus=self._event_bus,
            backtest_repository=self._backtest_repo,
            bar_repository=self._bar_repo,
        )

        result = await optimizer.optimize(config)

        await self._optimization_repo.save(result)

        return result
