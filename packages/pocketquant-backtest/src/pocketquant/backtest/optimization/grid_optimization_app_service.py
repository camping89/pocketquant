"""Grid optimizer - parallel parameter sweep for strategy optimization."""

import asyncio
import itertools
from datetime import UTC, datetime
from typing import Any

from pocketquant.backtest.domain import (
    BacktestMetrics,
    BacktestResult,
    OptimizationResult,
    OptimizationResultEntry,
)
from pocketquant.backtest.engine.backtest_app_service import BacktestAppService
from pocketquant.backtest.optimization.models.backtest_config import BacktestConfig
from pocketquant.backtest.optimization.models.optimization_config import OptimizationConfig
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.infrastructure.brokers.paper.paper_broker import PaperBroker
from pocketquant.core.persistence.repositories.bar_repository import BarRepository

logger = get_logger(__name__)


class GridOptimizationAppService:
    """Grid search optimizer for strategy parameter tuning.

    Runs multiple backtests in parallel with different parameter combinations,
    ranks results by target metric, and returns the best configuration.

    Features:
    - Parallel execution with semaphore-based concurrency control
    - Graceful handling of individual backtest failures
    - Results ranked by configurable target metric
    - Memory efficient - doesn't store full equity curves in optimization result

    Usage:
        optimizer = GridOptimizationAppService(event_bus, backtest_repo, bar_repo)
        result = await optimizer.optimize(config)
    """

    def __init__(
        self,
        event_bus: EventBus,
        backtest_repository: BacktestRepository,
        bar_repository: BarRepository,
    ) -> None:
        self._event_bus = event_bus
        self._backtest_repo = backtest_repository
        self._bar_repo = bar_repository

    async def optimize(self, config: OptimizationConfig) -> OptimizationResult:
        """Run grid optimization across all parameter combinations.

        Args:
            config: Optimization configuration with parameter grid.

        Returns:
            OptimizationResult with ranked results and best parameters.

        Raises:
            ValueError: If config validation fails.
        """
        # Validate before starting
        config.validate()

        optimization_id = generate_id_str()
        started_at = datetime.now(UTC)

        # Generate all parameter combinations
        combinations = self._generate_combinations(config.parameter_grid)
        total_combinations = len(combinations)

        logger.info(
            "optimization_starting",
            optimization_id=optimization_id,
            strategy_id=config.strategy_id,
            total_combinations=total_combinations,
            max_workers=config.max_workers,
        )

        # Run backtests in parallel with semaphore
        semaphore = asyncio.Semaphore(config.max_workers)
        tasks = [
            self._run_with_semaphore(semaphore, config, params, optimization_id)
            for params in combinations
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        completed_results: list[tuple[dict[str, Any], BacktestResult]] = []
        failed_count = 0

        for params, result in zip(combinations, results):
            if isinstance(result, BaseException):
                logger.warning(
                    "optimization_backtest_exception",
                    optimization_id=optimization_id,
                    params=params,
                    error=str(result),
                )
                failed_count += 1
            elif result.status == "failed":
                failed_count += 1
            else:
                completed_results.append((params, result))

        completed_at = datetime.now(UTC)

        if not completed_results:
            logger.error(
                "optimization_all_failed",
                optimization_id=optimization_id,
                total=total_combinations,
            )
            return OptimizationResult(
                id=optimization_id,
                strategy_id=config.strategy_id,
                config_snapshot=self._serialize_config(config),
                target_metric=config.target_metric,
                total_combinations=total_combinations,
                completed_combinations=0,
                failed_combinations=failed_count,
                results=[],
                best_parameters={},
                best_metrics=BacktestMetrics.empty(),
                started_at=started_at,
                completed_at=completed_at,
                status="failed",
                error_message="All backtests failed",
            )

        # Rank by target metric
        ranked = self._rank_results(completed_results, config.target_metric)

        # Build result entries
        result_entries = [
            OptimizationResultEntry(
                parameters=params,
                metrics=result.metrics,
                backtest_id=result.id,
                rank=rank + 1,
            )
            for rank, (params, result) in enumerate(ranked)
        ]

        best_params, best_result = ranked[0]

        logger.info(
            "optimization_completed",
            optimization_id=optimization_id,
            completed=len(completed_results),
            failed=failed_count,
            best_metric=round(getattr(best_result.metrics, config.target_metric), 4),
        )

        return OptimizationResult(
            id=optimization_id,
            strategy_id=config.strategy_id,
            config_snapshot=self._serialize_config(config),
            target_metric=config.target_metric,
            total_combinations=total_combinations,
            completed_combinations=len(completed_results),
            failed_combinations=failed_count,
            results=result_entries,
            best_parameters=best_params,
            best_metrics=best_result.metrics,
            started_at=started_at,
            completed_at=completed_at,
            status="completed",
        )

    async def _run_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        config: OptimizationConfig,
        params: dict[str, Any],
        optimization_id: str,
    ) -> BacktestResult:
        """Run a single backtest with semaphore concurrency control."""
        async with semaphore:
            # Create backtest config with these parameters
            backtest_config = BacktestConfig(
                strategy_id=config.strategy_id,
                symbol=config.symbol,
                interval=config.interval,
                start_date=config.start_date,
                end_date=config.end_date,
                initial_capital=config.initial_capital,
                slippage_bps=config.slippage_bps,
                commission_bps=config.commission_bps,
                replay_speed=0.0,  # Max speed for optimization
                parameters=params,
            )

            # Create fresh broker for this backtest
            broker = PaperBroker(
                initial_balance=config.initial_capital,
                slippage_percent=backtest_config.slippage_percent,
            )

            # Create runner (don't persist individual results during optimization)
            runner = BacktestAppService(
                event_bus=self._event_bus,
                broker=broker,
                backtest_repository=self._backtest_repo,
                bar_repository=self._bar_repo,
                persist_results=False,  # Optimization persists summary only
            )

            return await runner.run(backtest_config)

    def _generate_combinations(self, parameter_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
        """Generate all parameter combinations from grid."""
        if not parameter_grid:
            return [{}]

        param_names = list(parameter_grid.keys())
        param_values = list(parameter_grid.values())

        combinations = []
        for combo in itertools.product(*param_values):
            combinations.append(dict(zip(param_names, combo)))

        return combinations

    def _rank_results(
        self,
        results: list[tuple[dict[str, Any], BacktestResult]],
        target_metric: str,
    ) -> list[tuple[dict[str, Any], BacktestResult]]:
        """Rank results by target metric (descending - higher is better)."""
        return sorted(
            results,
            key=lambda x: getattr(x[1].metrics, target_metric, 0),
            reverse=True,
        )

    def _serialize_config(self, config: OptimizationConfig) -> dict[str, Any]:
        """Serialize optimization config for storage."""
        return {
            "strategy_id": config.strategy_id,
            "symbol": config.symbol,
            "interval": config.interval,
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
            "initial_capital": config.initial_capital,
            "slippage_bps": config.slippage_bps,
            "commission_bps": config.commission_bps,
            "parameter_grid": config.parameter_grid,
            "target_metric": config.target_metric,
            "max_workers": config.max_workers,
        }
