"""API routes for getting optimization results."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.backtesting.get_optimization.query import GetOptimizationQuery

router = APIRouter()


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
