"""Backtest API routes.

Two top-level routers:

* ``backtest_router``          (prefix ``/backtest``)    — run, optimize, results
* ``run_all_backtests_router`` (prefix ``/strategies``)  — fan-out per subscription
"""

from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.backtest.backtest_command_service import (
    BacktestCommandService,
    RunAllBacktestsCommand,
    RunBacktestCommand,
    RunOptimizationCommand,
)
from pocketquant.backtest.backtest_query_service import (
    BacktestQueryService,
    BacktestRequestStatusResponse,
    EnqueueBacktestResponse,
    GetBacktestQuery,
    GetOptimizationQuery,
    ListBacktestsQuery,
    OptimizationSummaryResponse,
)
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY

# ---------------------------------------------------------------------------
# backtest_router — /backtest prefix
# ---------------------------------------------------------------------------

backtest_router = APIRouter(prefix="/backtest", tags=["backtest"], route_class=DishkaRoute)


@backtest_router.get("/strategies")
async def list_available_strategies() -> list[str]:
    """Return strategy IDs available for backtesting."""
    return list(STRATEGY_REGISTRY.keys())


@backtest_router.post("/run", response_model=EnqueueBacktestResponse, status_code=202)
async def run_backtest(
    cmd: RunBacktestCommand,
    cmd_svc: FromDishka[BacktestCommandService],
) -> dict:
    """Enqueue a single backtest run. Returns a request id for polling.

    Execution is async: the headless app's worker runs the engine and embeds the
    result in the request doc. Poll ``GET /backtest/requests/{request_id}``.
    """
    return await cmd_svc.run(cmd)


@backtest_router.get("/requests/{request_id}", response_model=BacktestRequestStatusResponse)
async def get_backtest_request(
    request_id: str,
    query_svc: FromDishka[BacktestQueryService],
) -> dict:
    """Poll a single backtest request's status + embedded result."""
    return await query_svc.get_request_status(request_id)


@backtest_router.post("/optimize", response_model=OptimizationSummaryResponse)
async def run_optimization(
    cmd: RunOptimizationCommand,
    cmd_svc: FromDishka[BacktestCommandService],
) -> dict:
    """Run grid optimization across parameter combinations.

    Tests all combinations of parameters and returns ranked results.
    Maximum 1000 combinations allowed.
    """
    result = await cmd_svc.optimize(cmd)
    return {
        "id": str(result.id),
        "strategy_code": result.strategy_code,
        "status": result.status,
        "total_combinations": result.total_combinations,
        "completed_combinations": result.completed_combinations,
        "failed_combinations": result.failed_combinations,
        "target_metric": result.target_metric,
        "best_parameters": result.best_parameters,
        "best_metric_value": getattr(result.best_metrics, result.target_metric, 0),
    }


@backtest_router.get("/{run_id}")
async def get_backtest(
    run_id: str,
    query_svc: FromDishka[BacktestQueryService],
) -> dict:
    """Get a specific backtest result by ID.

    Returns full result including equity curve and trade history.
    """
    result = await query_svc.get_result(GetBacktestQuery(run_id=run_id))
    return result.to_dict()


@backtest_router.get("/{run_id}/equity")
async def get_backtest_equity(
    run_id: str,
    query_svc: FromDishka[BacktestQueryService],
) -> dict:
    """Get equity curve data for a backtest.

    Returns only the equity curve for charting purposes.
    """
    result = await query_svc.get_result(GetBacktestQuery(run_id=run_id))
    return {
        "run_id": str(result.id),
        "equity_curve": [
            {"timestamp": p.timestamp.isoformat(), "equity": p.equity, "drawdown": p.drawdown}
            for p in result.equity_curve
        ],
    }


@backtest_router.get("/strategy/{strategy_id}")
async def list_backtests(
    strategy_id: str,
    query_svc: FromDishka[BacktestQueryService],
    limit: int = 20,
    include_failed: bool = False,
) -> list[dict[str, Any]]:
    """List backtest results for a strategy.

    Returns summary information without full equity curves.
    """
    results = await query_svc.list_results(
        ListBacktestsQuery(
            strategy_id=strategy_id,
            limit=limit,
            include_failed=include_failed,
        )
    )
    return [
        {
            "id": str(r.id),
            "strategy_code": r.strategy_code,
            "status": r.status,
            "metrics": r.metrics.to_dict(),
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat(),
            "parameters": r.parameters,
            "error_message": r.error_message,
        }
        for r in results
    ]


@backtest_router.get("/optimization/{optimization_id}")
async def get_optimization(
    optimization_id: str,
    query_svc: FromDishka[BacktestQueryService],
) -> dict:
    """Get optimization result by ID.

    Returns full optimization result with all ranked parameter combinations.
    """
    result = await query_svc.get_optimization(GetOptimizationQuery(optimization_id=optimization_id))
    return result.to_dict()


# ---------------------------------------------------------------------------
# run_all_backtests_router — /strategies prefix (separate mount)
# ---------------------------------------------------------------------------

run_all_backtests_router = APIRouter(
    prefix="/strategies", tags=["strategies"], route_class=DishkaRoute
)


@run_all_backtests_router.post("/{strategy_code}/run-all-backtests", status_code=202)
async def run_all_backtests(
    strategy_code: str,
    cmd_svc: FromDishka[BacktestCommandService],
) -> dict:
    """Enqueue an immediate backtest job for every subscription of the strategy template."""
    return await cmd_svc.run_all(RunAllBacktestsCommand(strategy_id=strategy_code))
