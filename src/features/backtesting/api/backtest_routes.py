"""Backtest API routes - REST endpoints for backtest execution and results."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.backtesting.handlers import (
    GetBacktestQuery,
    GetOptimizationQuery,
    ListBacktestsQuery,
    RunBacktestCommand,
    RunOptimizationCommand,
)

router = APIRouter(prefix="/backtest", tags=["backtest"])


# === Response Models ===


class BacktestMetricsResponse(BaseModel):
    """Backtest performance metrics."""

    total_return: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_commission: float


class BacktestSummaryResponse(BaseModel):
    """Summary of a backtest run (without full equity curve)."""

    id: str
    strategy_id: str
    status: str
    metrics: BacktestMetricsResponse
    started_at: str
    completed_at: str
    error_message: str | None = None


class RunBacktestResponse(BaseModel):
    """Response after submitting backtest."""

    run_id: str
    status: str
    metrics: BacktestMetricsResponse | None = None


class OptimizationSummaryResponse(BaseModel):
    """Summary of optimization run."""

    id: str
    strategy_id: str
    status: str
    total_combinations: int
    completed_combinations: int
    failed_combinations: int
    target_metric: str
    best_parameters: dict[str, Any]
    best_metric_value: float


# === Endpoints ===


@router.post("/run", response_model=RunBacktestResponse)
async def run_backtest(
    cmd: RunBacktestCommand,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    """Execute a single backtest run.

    Runs the specified strategy over historical data and returns performance metrics.
    """
    result = await mediator.send(cmd)

    return {
        "run_id": result.id,
        "status": result.status,
        "metrics": result.metrics.to_dict() if result.status == "completed" else None,
    }


@router.post("/optimize", response_model=OptimizationSummaryResponse)
async def run_optimization(
    cmd: RunOptimizationCommand,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    """Run grid optimization across parameter combinations.

    Tests all combinations of parameters and returns ranked results.
    Maximum 1000 combinations allowed.
    """
    try:
        result = await mediator.send(cmd)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "id": result.id,
        "strategy_id": result.strategy_id,
        "status": result.status,
        "total_combinations": result.total_combinations,
        "completed_combinations": result.completed_combinations,
        "failed_combinations": result.failed_combinations,
        "target_metric": result.target_metric,
        "best_parameters": result.best_parameters,
        "best_metric_value": getattr(result.best_metrics, result.target_metric, 0),
    }


@router.get("/{run_id}")
async def get_backtest(
    run_id: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    """Get a specific backtest result by ID.

    Returns full result including equity curve and trade history.
    """
    query = GetBacktestQuery(run_id=run_id)
    result = await mediator.send(query)

    if not result:
        raise HTTPException(status_code=404, detail=f"Backtest not found: {run_id}")

    return result.to_dict()


@router.get("/{run_id}/equity")
async def get_backtest_equity(
    run_id: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    """Get equity curve data for a backtest.

    Returns only the equity curve for charting purposes.
    """
    query = GetBacktestQuery(run_id=run_id)
    result = await mediator.send(query)

    if not result:
        raise HTTPException(status_code=404, detail=f"Backtest not found: {run_id}")

    return {
        "run_id": result.id,
        "equity_curve": [
            {"timestamp": p.timestamp.isoformat(), "equity": p.equity, "drawdown": p.drawdown}
            for p in result.equity_curve
        ],
    }


@router.get("/optimization/{optimization_id}")
async def get_optimization(
    optimization_id: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    """Get optimization result by ID.

    Returns full optimization result with all ranked parameter combinations.
    """
    query = GetOptimizationQuery(optimization_id=optimization_id)
    result = await mediator.send(query)

    if not result:
        raise HTTPException(status_code=404, detail=f"Optimization not found: {optimization_id}")

    return result.to_dict()


@router.get("/strategy/{strategy_id}")
async def list_backtests(
    strategy_id: str,
    mediator: Annotated[Mediator, Depends(get_mediator)],
    limit: int = 20,
    include_failed: bool = False,
) -> list[dict]:
    """List backtest results for a strategy.

    Returns summary information without full equity curves.
    """
    query = ListBacktestsQuery(
        strategy_id=strategy_id,
        limit=limit,
        include_failed=include_failed,
    )
    results = await mediator.send(query)

    return [
        {
            "id": r.id,
            "strategy_id": r.strategy_id,
            "status": r.status,
            "metrics": r.metrics.to_dict(),
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat(),
            "parameters": r.parameters,
            "error_message": r.error_message,
        }
        for r in results
    ]
