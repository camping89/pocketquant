"""Route for updating a tracked symbol — admin only."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends
from pocketquant.api.common.symbol_validation import validate_symbol_pair
from pocketquant.api.market_data.handlers.tracked_symbols.update.command import (
    UpdateTrackedSymbolCommand,
)
from pocketquant.api.middleware.admin_auth_middleware import verify_admin_token
from pocketquant.core.common.mediator import Mediator

router = APIRouter(route_class=DishkaRoute)


@router.put(
    "/tracked-symbols/{exchange}/{symbol}",
    response_model=dict,
    dependencies=[Depends(verify_admin_token)],
)
async def update_tracked_symbol(
    exchange: str,
    symbol: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Update metadata for a tracked symbol. Requires X-Admin-Token."""
    exchange, symbol = validate_symbol_pair(exchange, symbol)
    cmd = UpdateTrackedSymbolCommand(exchange=exchange, symbol=symbol)
    return await mediator.send(cmd)
