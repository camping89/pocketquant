"""Route for updating a tracked symbol — admin only."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends
from pocketquant.api.common.symbol_validation import validate_composite_symbol
from pocketquant.api.market_data.handlers.tracked_symbols.update.command import (
    UpdateTrackedSymbolCommand,
)
from pocketquant.api.middleware.admin_auth_middleware import verify_admin_token
from pocketquant.core.common.mediator import Mediator

router = APIRouter(route_class=DishkaRoute)


@router.put(
    "/tracked-symbols/{symbol}",
    response_model=dict,
    dependencies=[Depends(verify_admin_token)],
)
async def update_tracked_symbol(
    symbol: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Update metadata for a tracked symbol. Requires X-Admin-Token.

    ``symbol`` path param is URL-encoded composite ``{code}:{exchange}``
    (e.g. ``BTCUSDT%3ABINANCE``).
    """
    symbol = validate_composite_symbol(symbol)
    cmd = UpdateTrackedSymbolCommand(symbol=symbol)
    return await mediator.send(cmd)
