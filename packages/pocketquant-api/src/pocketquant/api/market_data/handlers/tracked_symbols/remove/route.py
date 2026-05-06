"""Route for removing a tracked symbol — admin only."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends
from pocketquant.api.common.symbol_validation import validate_symbol_pair
from pocketquant.api.market_data.handlers.tracked_symbols.remove.command import RemoveTrackedSymbolCommand
from pocketquant.api.middleware.admin_auth_middleware import verify_admin_token
from pocketquant.core.common.mediator import Mediator

router = APIRouter(route_class=DishkaRoute)


@router.delete(
    "/tracked-symbols/{exchange}/{symbol}",
    response_model=dict,
    dependencies=[Depends(verify_admin_token)],
)
async def remove_tracked_symbol(
    exchange: str,
    symbol: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Remove (exchange, symbol) from tracked list. Requires X-Admin-Token."""
    exchange, symbol = validate_symbol_pair(exchange, symbol)
    cmd = RemoveTrackedSymbolCommand(exchange=exchange, symbol=symbol)
    return await mediator.send(cmd)
