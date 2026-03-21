"""API route for getting all active quotes."""


from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.core.common.mediator import Mediator
from pocketquant.api.market_data.handlers.quotes.get_all.query import GetAllQuotesQuery
from pocketquant.api.market_data.handlers.quotes.get_latest.route import QuoteResponse

router = APIRouter(route_class=DishkaRoute)


@router.get("/all", response_model=list[QuoteResponse])
async def get_all_quotes(
    mediator: FromDishka[Mediator],
) -> list[QuoteResponse]:
    query = GetAllQuotesQuery()
    results = await mediator.send(query)
    return [QuoteResponse.from_result(r) for r in results]
