"""API route for starting the quote feed."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.market_data.quotes.start_feed.command import StartQuoteFeedCommand

router = APIRouter()


@router.post("/start")
async def start_quote_service(
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    cmd = StartQuoteFeedCommand()
    return await mediator.send(cmd)
