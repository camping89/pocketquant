"""Route for adding a tracked symbol — admin only."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends

from pocketquant.bff.middleware.admin_auth_middleware import verify_admin_token
from pocketquant.core.common.mediator import Mediator
from pocketquant.engine.market_data.handlers.tracked_symbols.add.command import (
    AddTrackedSymbolCommand,
)

router = APIRouter(route_class=DishkaRoute)


@router.post("/tracked-symbols", response_model=dict, dependencies=[Depends(verify_admin_token)])
async def add_tracked_symbol(
    cmd: AddTrackedSymbolCommand,
    mediator: FromDishka[Mediator],
) -> dict:
    """Add (exchange, symbol) to tracked list. Idempotent. Requires X-Admin-Token."""
    return await mediator.send(cmd)
