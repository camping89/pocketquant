"""API routes for getting optimization results."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Mediator
from pocketquant.backtest.handlers.get_optimization.query import GetOptimizationQuery

router = APIRouter(route_class=DishkaRoute)


@router.get("/optimization/{optimization_id}")
async def get_optimization(
    optimization_id: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Get optimization result by ID.

    Returns full optimization result with all ranked parameter combinations.
    """
    query = GetOptimizationQuery(optimization_id=optimization_id)
    result = await mediator.send(query)

    if not result:
        raise NotFoundError(f"Optimization not found: {optimization_id}")

    return result.to_dict()
