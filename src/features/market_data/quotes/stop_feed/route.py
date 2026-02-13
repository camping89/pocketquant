"""API route for stopping the quote feed."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.mediator import Mediator
from src.common.mediator.dependencies import get_mediator
from src.features.market_data.quotes.stop_feed.command import StopQuoteFeedCommand

router = APIRouter()


@router.post("/stop")
async def stop_quote_service(
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    cmd = StopQuoteFeedCommand()
    return await mediator.send(cmd)
