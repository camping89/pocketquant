"""Route for removing a tracked symbol — admin only."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends
from pocketquant.api.common.symbol_validation import validate_composite_symbol
from pocketquant.api.market_data.handlers.tracked_symbols.remove.command import (
    RemoveTrackedSymbolCommand,
)
from pocketquant.api.middleware.admin_auth_middleware import verify_admin_token
from pocketquant.core.common.mediator import Mediator

router = APIRouter(route_class=DishkaRoute)


@router.delete(
    "/tracked-symbols/{symbol}",
    response_model=dict,
    dependencies=[Depends(verify_admin_token)],
)
async def remove_tracked_symbol(
    symbol: str,
    mediator: FromDishka[Mediator],
) -> dict:
    """Remove composite symbol from tracked list. Requires X-Admin-Token.

    ``symbol`` path param is URL-encoded composite ``{code}:{exchange}``
    (e.g. ``BTCUSDT%3ABINANCE``).
    """
    symbol = validate_composite_symbol(symbol)
    cmd = RemoveTrackedSymbolCommand(symbol=symbol)
    return await mediator.send(cmd)
