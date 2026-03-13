"""API route for stopping the quote feed."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from src.common.mediator import Mediator
from src.features.market_data.quotes.stop_feed.command import StopQuoteFeedCommand

router = APIRouter(route_class=DishkaRoute)


@router.post("/stop")
async def stop_quote_service(
    mediator: FromDishka[Mediator],
) -> dict:
    cmd = StopQuoteFeedCommand()
    return await mediator.send(cmd)
