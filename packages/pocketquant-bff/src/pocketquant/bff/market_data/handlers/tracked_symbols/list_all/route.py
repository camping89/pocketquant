"""Route for listing all tracked symbols — public read endpoint."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.core.common.mediator import Mediator
from pocketquant.execution.market_data.handlers.tracked_symbols.list_all.query import (
    ListTrackedSymbolsQuery,
)

router = APIRouter(route_class=DishkaRoute)


@router.get("/tracked-symbols", response_model=list[dict])
async def list_tracked_symbols(mediator: FromDishka[Mediator]) -> list[dict]:
    """List all symbols tracked for live data pipelines. No auth required."""
    return await mediator.send(ListTrackedSymbolsQuery())
