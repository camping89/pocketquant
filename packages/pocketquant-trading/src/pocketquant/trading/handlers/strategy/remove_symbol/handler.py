"""RemoveSymbolHandler — cancel job, delete backtest cache, delete subscription."""

from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.infrastructure.scheduling.scheduler import JobScheduler
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.trading.handlers.strategy.remove_symbol.command import RemoveSymbolCommand
from pocketquant.trading.persistence.strategy_subscription_repository import (
    StrategySubscriptionRepository,
)


@handles(RemoveSymbolCommand)
class RemoveSymbolHandler(Handler[RemoveSymbolCommand, None]):
    """Handle RemoveSymbolCommand — unload instance + cancel job + delete subscription + backtest."""

    def __init__(
        self,
        job_scheduler: JobScheduler,
        backtest_repository: BacktestRepository,
        strategy_subscription_repository: StrategySubscriptionRepository,
        strategy_app_service: StrategyAppService,
    ) -> None:
        self._scheduler = job_scheduler
        self._bt_repo = backtest_repository
        self._sub_repo = strategy_subscription_repository
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
