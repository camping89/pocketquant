"""RemoveSymbolHandler — cancel job, delete backtest cache, delete subscription."""

from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.infrastructure.scheduling.scheduler import JobScheduler
from pocketquant.trading.handlers.strategy.remove_symbol.command import RemoveSymbolCommand
from pocketquant.trading.persistence.strategy_subscription_repository import (
    StrategySubscriptionRepository,
)


@handles(RemoveSymbolCommand)
class RemoveSymbolHandler(Handler[RemoveSymbolCommand, None]):
    """Handle RemoveSymbolCommand — cascade cancel job + delete subscription + backtest."""

    def __init__(
        self,
        job_scheduler: JobScheduler,
        backtest_repository: BacktestRepository,
        strategy_subscription_repository: StrategySubscriptionRepository,
    ) -> None:
        self._scheduler = job_scheduler
        self._bt_repo = backtest_repository
        self._sub_repo = strategy_subscription_repository

    async def handle(self, request: RemoveSymbolCommand) -> None:
        """Cancel pending job (if any), delete cached backtest, delete subscription."""
        # Cancel scheduled job — swallow if not found (may have already finished)
        try:
            self._scheduler.remove_job(f"bt:{request.sub_id}")
        except Exception:
            pass

        await self._bt_repo.delete_by_subscription(request.sub_id)
        await self._sub_repo.delete(request.sub_id)
