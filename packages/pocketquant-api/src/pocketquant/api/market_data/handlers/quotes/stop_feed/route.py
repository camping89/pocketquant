"""API route for stopping the quote feed."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.api.market_data.handlers.quotes.stop_feed.command import StopQuoteFeedCommand
from pocketquant.core.common.mediator import Mediator

router = APIRouter(route_class=DishkaRoute)


@router.post("/stop")
async def stop_quote_service(
    mediator: FromDishka[Mediator],
) -> dict:
    cmd = StopQuoteFeedCommand()
    return await mediator.send(cmd)
