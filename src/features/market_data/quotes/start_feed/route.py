"""API route for starting the quote feed."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from src.common.mediator import Mediator
from src.features.market_data.quotes.start_feed.command import StartQuoteFeedCommand

router = APIRouter(route_class=DishkaRoute)


@router.post("/start")
async def start_quote_service(
    mediator: FromDishka[Mediator],
) -> dict:
    cmd = StartQuoteFeedCommand()
    return await mediator.send(cmd)
