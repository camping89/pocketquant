"""ListSubscriptionsHandler — return subscriptions enriched with backtest status + is_running."""

from pocketquant.infrastructure.persistence.repositories.backtest_repository import BacktestRepository
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.trading.handlers.strategy.list_symbols.query import ListSymbolsQuery
from pocketquant.infrastructure.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)


@handles(ListSymbolsQuery)
class ListSymbolsHandler(Handler[ListSymbolsQuery, list]):
    """Handle ListSymbolsQuery — join subscriptions with backtest status + live is_running."""

    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        backtest_repository: BacktestRepository,
        strategy_app_service: StrategyAppService,
    ) -> None:
        self._sub_repo = subscription_repository
        self._bt_repo = backtest_repository
        self._strategy_service = strategy_app_service

    async def handle(self, request: ListSymbolsQuery) -> list:
        """List subscriptions filtered by strategy_code (or all if None).

        Computes ``is_running`` from the live StrategyAppService instance keyed
        by ``sub.id``. Uses a single batched DB call for backtest statuses.
        """
        if request.strategy_code is None:
            subs = await self._sub_repo.list_all()
        else:
            subs = await self._sub_repo.list_by_strategy_code(request.strategy_code)

        if not subs:
            return []

        sub_ids = [sub.id for sub in subs]
        bt_statuses = await self._bt_repo.get_subscription_statuses(sub_ids)

        return [
            {
                "id": sub.id,
                "strategy_code": sub.strategy_code,
                "symbol": sub.symbol,
                "interval": sub.interval.value,
                "created_at": sub.created_at.isoformat(),
                "is_running": self._is_running(sub.id),
                "backtest": bt_statuses.get(sub.id),
            }
            for sub in subs
        ]

    def _is_running(self, sub_id: str) -> bool:
        strategy = self._strategy_service.get_strategy(sub_id)
        return bool(strategy and strategy.is_running)
