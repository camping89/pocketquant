"""RunAllBacktestsHandler — enqueue one-off backtest job per subscription."""

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.infrastructure.scheduling.scheduler import JobScheduler
from pocketquant.trading.handlers.strategy.run_all_backtests.command import RunAllBacktestsCommand
from pocketquant.trading.persistence.strategy_subscription_repository import (
    StrategySubscriptionRepository,
)

_JOB_MODULE = "pocketquant.trading.jobs.backtest_jobs:run_subscription_backtest"


@handles(RunAllBacktestsCommand)
class RunAllBacktestsHandler(Handler[RunAllBacktestsCommand, dict]):
    """Handle RunAllBacktestsCommand — fan-out immediate one-off jobs via scheduler."""

    def __init__(
        self,
        strategy_subscription_repository: StrategySubscriptionRepository,
        job_scheduler: JobScheduler,
    ) -> None:
        self._sub_repo = strategy_subscription_repository
        self._scheduler = job_scheduler

    async def handle(self, request: RunAllBacktestsCommand) -> dict:
        """Enqueue a date-triggered (immediate) backtest job for each subscription."""
        subs = await self._sub_repo.list_by_strategy(request.strategy_id)
        if not subs:
            raise NotFoundError(
                f"No subscriptions found for strategy '{request.strategy_id}'. "
                "Add symbols via POST /{strategy_id}/symbols first."
            )

        job_ids = []
        for sub in subs:
            job_id = f"bt:{sub.id}"
            self._scheduler.add_one_off_job(
                _JOB_MODULE,
                job_id=job_id,
                subscription_id=sub.id,
            )
            job_ids.append(job_id)

        return {"job_ids": job_ids}
