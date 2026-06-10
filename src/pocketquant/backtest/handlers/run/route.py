from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pydantic import BaseModel

from pocketquant.backtest.handlers.run.command import RunBacktestCommand
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)

router = APIRouter(route_class=DishkaRoute)


class EnqueueBacktestResponse(BaseModel):
    """Response after enqueuing a single backtest — FE polls for the result."""

    request_id: str


class BacktestRequestStatusResponse(BaseModel):
    """Poll response for a single backtest request.

    ``result`` carries the assembled FE payload (run_id/status/metrics/positions)
    once ``status == 'done'``; it is None while pending/running and on failure.
    """

    request_id: str
    status: str
    result: dict | None = None
    error: str | None = None


@router.post("/run", response_model=EnqueueBacktestResponse, status_code=202)
async def run_backtest(
    cmd: RunBacktestCommand,
    mediator: FromDishka[Mediator],
) -> dict:
    """Enqueue a single backtest run. Returns a request id for polling.

    Execution is async: the headless app's worker runs the engine and embeds the
    result in the request doc. Poll ``GET /backtest/requests/{request_id}``.
    """
    return await mediator.send(cmd)


@router.get("/requests/{request_id}", response_model=BacktestRequestStatusResponse)
async def get_backtest_request(
    request_id: str,
    request_repo: FromDishka[BacktestRequestRepository],
) -> dict:
    """Poll a single backtest request's status + embedded result."""
    bt_request = await request_repo.get(request_id)
    if bt_request is None:
        raise NotFoundError(f"Backtest request not found: {request_id}")

    return {
        "request_id": bt_request.id,
        "status": bt_request.status,
        "result": bt_request.result,
        "error": bt_request.error,
    }
