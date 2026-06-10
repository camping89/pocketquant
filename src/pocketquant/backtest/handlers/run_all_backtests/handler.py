"""RunAllBacktestsHandler — enqueue one backtest request per subscription."""

from datetime import UTC, datetime

from pocketquant.backtest.handlers.run_all_backtests.command import RunAllBacktestsCommand
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.domain.backtest.request import BacktestRequest
from pocketquant.core.infra.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)


@handles(RunAllBacktestsCommand)
class RunAllBacktestsHandler(Handler[RunAllBacktestsCommand, dict]):
    """Enqueue a backtest request for every subscription of a strategy template.

    Pure DB write — no scheduler. The headless app's BacktestRequestWorker
    claims and runs each request. bff can therefore call this without owning a
    JobScheduler.
    """

    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        backtest_request_repository: BacktestRequestRepository,
    ) -> None:
        self._sub_repo = subscription_repository
        self._request_repo = backtest_request_repository

    async def handle(self, request: RunAllBacktestsCommand) -> dict:
        subs = await self._sub_repo.list_by_strategy_code(request.strategy_id)
        if not subs:
            raise NotFoundError(
                f"No subscriptions found for strategy '{request.strategy_id}'. "
                "Add symbols via POST /{strategy_id}/symbols first."
            )

        # FE (strategy-api.ts runAllBacktests) reads `job_ids`; keep the key name
        # so the run-all path needs zero FE change — it now carries request ids.
        #
        # Deterministic id per subscription + upsert enqueue makes two concurrent
        # run-all fan-outs collapse to one pending request per sub (preserving the
        # old APScheduler replace_existing dedup), instead of duplicating compute.
        job_ids = []
        for sub in subs:
            bt_request = BacktestRequest(
                id=f"bt:{sub.id}",
                kind="subscription",
                status="pending",
                requested_at=datetime.now(UTC),
                sub_id=sub.id,
                strategy_code=sub.strategy_code,
            )
            await self._request_repo.enqueue(bt_request)
            job_ids.append(bt_request.id)

        return {"job_ids": job_ids}
