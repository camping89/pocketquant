"""ListSymbols API route — GET /{strategy_id}/symbols."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.core.common.mediator import Mediator
from pocketquant.trading.handlers.strategy.list_symbols.query import ListSymbolsQuery

router = APIRouter(route_class=DishkaRoute)


@router.get("/{strategy_id}/symbols")
async def list_symbols(
    strategy_id: str,
    mediator: FromDishka[Mediator],
) -> list:
    """List all symbol subscriptions for a strategy with their backtest status."""
    return await mediator.send(ListSymbolsQuery(strategy_id=strategy_id))
