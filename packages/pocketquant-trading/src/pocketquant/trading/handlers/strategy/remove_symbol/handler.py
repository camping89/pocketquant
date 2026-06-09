"""RemoveSymbolHandler — cancel job, delete backtest cache, delete subscription."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.execution.app_services.strategy_app_service import StrategyAppService
from pocketquant.infrastructure.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.infrastructure.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.infrastructure.scheduling.scheduler import JobScheduler
from pocketquant.trading.handlers.strategy.remove_symbol.command import RemoveSymbolCommand


@handles(RemoveSymbolCommand)
class RemoveSymbolHandler(Handler[RemoveSymbolCommand, None]):
    """Handle RemoveSymbolCommand — unload instance, cancel job, delete sub + backtest."""

    def __init__(
        self,
        job_scheduler: JobScheduler,
        backtest_repository: BacktestRepository,
        subscription_repository: SubscriptionRepository,
        strategy_app_service: StrategyAppService,
    ) -> None:
        self._scheduler = job_scheduler
        self._bt_repo = backtest_repository
        self._sub_repo = subscription_repository
        self._strategy_service = strategy_app_service

    async def handle(self, request: RemoveSymbolCommand) -> None:
        """Unload the per-subscription strategy instance and cascade-delete state."""
        try:
            self._scheduler.remove_job(f"bt:{request.sub_id}")
        except Exception:
            pass

        if self._strategy_service.get_strategy(request.sub_id) is not None:
            await self._strategy_service.unload_strategy(request.sub_id)

        await self._bt_repo.delete_by_subscription(request.sub_id)
        await self._sub_repo.delete(request.sub_id)
