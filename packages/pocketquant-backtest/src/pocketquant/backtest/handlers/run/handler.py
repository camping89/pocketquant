"""RunBacktestHandler — enqueue a single ad-hoc backtest request.

Pure DB write: persist a ``single`` BacktestRequest and return its id. The
headless app's BacktestRequestWorker claims it, runs the engine via the shared
dispatch, and embeds the FE response in the request doc. FE polls
``GET /backtest/requests/{id}`` for the result.
"""

from datetime import UTC, datetime

from pocketquant.backtest.handlers.run.command import RunBacktestCommand
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.domain.backtest.request import BacktestRequest
from pocketquant.infrastructure.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)


@handles(RunBacktestCommand)
class RunBacktestHandler(Handler[RunBacktestCommand, dict]):
    def __init__(self, backtest_request_repository: BacktestRequestRepository) -> None:
        self._request_repo = backtest_request_repository

    async def handle(self, request: RunBacktestCommand) -> dict:
        config = {
            "strategy_code": request.strategy_id,
            "symbol": request.symbol,
            "interval": request.interval,
            "start_date": request.start_date.isoformat(),
            "end_date": request.end_date.isoformat(),
            "initial_capital": request.initial_capital,
            "slippage_bps": request.slippage_bps,
            "commission_bps": request.commission_bps,
            "parameters": request.parameters or {},
        }
        bt_request = BacktestRequest(
            id=generate_id_str(),
            kind="single",
            status="pending",
            requested_at=datetime.now(UTC),
            strategy_code=request.strategy_id,
            config=config,
        )
        await self._request_repo.enqueue(bt_request)
        return {"request_id": bt_request.id}
