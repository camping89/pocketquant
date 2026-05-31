"""DeleteStrategyHandler — cascade cancel jobs, delete backtests, subs, unload strategy."""

from pocketquant.infrastructure.persistence.repositories.backtest_repository import BacktestRepository
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.infrastructure.scheduling.scheduler import JobScheduler
from pocketquant.execution.app_services.strategy_app_service import StrategyAppService
from pocketquant.trading.handlers.strategy.delete.command import DeleteStrategyCommand
from pocketquant.infrastructure.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)


@handles(DeleteStrategyCommand)
class DeleteStrategyHandler(Handler[DeleteStrategyCommand, None]):
    """Handle DeleteStrategyCommand — full cascade delete for a strategy.

    Order:
      1. Cancel all scheduled backtest jobs for this strategy's subscriptions.
      2. Delete all backtest docs keyed by strategy_id.
      3. Delete all subscriptions.
      4. Unload strategy from in-memory engine (no-op if already unloaded).
    """

    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        backtest_repository: BacktestRepository,
        job_scheduler: JobScheduler,
        strategy_app_service: StrategyAppService,
    ) -> None:
        self._sub_repo = subscription_repository
        self._bt_repo = backtest_repository
        self._scheduler = job_scheduler
        self._strategy_service = strategy_app_service

    async def handle(self, request: DeleteStrategyCommand) -> None:
        subs = await self._sub_repo.list_by_strategy_code(request.strategy_id)

        # 1. Cancel scheduled jobs and unload per-subscription strategy instances
        for sub in subs:
            try:
                self._scheduler.remove_job(f"bt:{sub.id}")
            except Exception:
                pass
            if self._strategy_service.get_strategy(sub.id) is not None:
                try:
                    await self._strategy_service.unload_strategy(sub.id)
                except Exception:
                    pass

        # 2. Delete all cached backtest docs for this strategy template
        await self._bt_repo.delete_by_strategy_code(request.strategy_id)

        # 3. Delete all subscriptions
        await self._sub_repo.delete_by_strategy_code(request.strategy_id)

        # 4. Also unload any legacy template-keyed instance (pre-refactor data)
        if self._strategy_service.get_strategy(request.strategy_id) is not None:
            try:
                await self._strategy_service.unload_strategy(request.strategy_id)
            except Exception:
                pass
