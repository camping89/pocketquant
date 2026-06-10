from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pydantic import BaseModel

from pocketquant.backtest.handlers.optimize.command import RunOptimizationCommand
from pocketquant.core.common.mediator import Mediator

router = APIRouter(route_class=DishkaRoute)


class OptimizationSummaryResponse(BaseModel):
    """Summary of optimization run."""

    id: str
    strategy_code: str
    status: str
    total_combinations: int
    completed_combinations: int
    failed_combinations: int
    target_metric: str
    best_parameters: dict[str, Any]
    best_metric_value: float


@router.post("/optimize", response_model=OptimizationSummaryResponse)
async def run_optimization(
    cmd: RunOptimizationCommand,
    mediator: FromDishka[Mediator],
) -> dict:
    """Run grid optimization across parameter combinations.

    Tests all combinations of parameters and returns ranked results.
    Maximum 1000 combinations allowed.
    """
    result = await mediator.send(cmd)

    return {
        "id": result.id,
        "strategy_code": result.strategy_code,
        "status": result.status,
        "total_combinations": result.total_combinations,
        "completed_combinations": result.completed_combinations,
        "failed_combinations": result.failed_combinations,
        "target_metric": result.target_metric,
        "best_parameters": result.best_parameters,
        "best_metric_value": getattr(result.best_metrics, result.target_metric, 0),
    }
