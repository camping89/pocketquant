"""DeleteStrategyHandler — cascade cancel jobs, delete backtests, subs, unload strategy."""

from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.infrastructure.scheduling.scheduler import JobScheduler
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.trading.handlers.strategy.delete.command import DeleteStrategyCommand
from pocketquant.trading.persistence.strategy_subscription_repository import (
    StrategySubscriptionRepository,
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
        strategy_subscription_repository: StrategySubscriptionRepository,
        backtest_repository: BacktestRepository,
        job_scheduler: JobScheduler,
        strategy_app_service: StrategyAppService,
    ) -> None:
        self._sub_repo = strategy_subscription_repository
        self._bt_repo = backtest_repository
        self._scheduler = job_scheduler
        self._strategy_service = strategy_app_service

    async def handle(self, request: DeleteStrategyCommand) -> None:
        """Execute cascade delete for the strategy and all associated data."""
        # 1. Cancel any pending backtest jobs for this strategy's subscriptions
        subs = await self._sub_repo.list_by_strategy(request.strategy_id)
        for sub in subs:
            try:
                self._scheduler.remove_job(f"bt:{sub.id}")
            except Exception:
                pass  # already finished or never scheduled

        # 2. Delete all cached backtest docs for this strategy
        await self._bt_repo.delete_by_strategy(request.strategy_id)

        # 3. Delete all subscriptions
        await self._sub_repo.delete_by_strategy(request.strategy_id)

        # 4. Unload from in-memory engine (no-op if not loaded — stop_strategy guards this)
        try:
            await self._strategy_service.unload_strategy(request.strategy_id)
        except Exception:
            pass
