"""ListSubscriptions API route — GET /subscriptions/."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.list_symbols.query import ListSymbolsQuery

router = APIRouter(route_class=DishkaRoute)


@router.get("/")
async def list_subscriptions(
    mediator: FromDishka[Mediator],
    strategy_code: str | None = None,
) -> list:
    """List subscriptions (optionally filter by strategy_code) with backtest + live status."""
    return await mediator.send(ListSymbolsQuery(strategy_code=strategy_code))
