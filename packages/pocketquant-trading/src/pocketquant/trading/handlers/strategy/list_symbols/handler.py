"""ListSymbolsHandler — return subscriptions enriched with backtest status."""

from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.trading.handlers.strategy.list_symbols.query import ListSymbolsQuery
from pocketquant.trading.persistence.strategy_subscription_repository import (
    StrategySubscriptionRepository,
)


@handles(ListSymbolsQuery)
class ListSymbolsHandler(Handler[ListSymbolsQuery, list]):
    """Handle ListSymbolsQuery — join subscriptions with lightweight backtest status."""

    def __init__(
        self,
        strategy_subscription_repository: StrategySubscriptionRepository,
        backtest_repository: BacktestRepository,
    ) -> None:
        self._sub_repo = strategy_subscription_repository
        self._bt_repo = backtest_repository

    async def handle(self, request: ListSymbolsQuery) -> list:
        """Return list of subscription dicts with nested backtest status or null.

        Uses a single batched DB call instead of N per-sub queries (M2 fix).
        """
        subs = await self._sub_repo.list_by_strategy(request.strategy_id)

        if not subs:
            return []

        sub_ids = [sub.id for sub in subs]
        bt_statuses = await self._bt_repo.get_subscription_statuses(sub_ids)

        return [
            {
                "id": sub.id,
                "strategy_id": sub.strategy_id,
                "symbol": sub.symbol,
                "exchange": sub.exchange,
                "interval": sub.interval.value,
                "created_at": sub.created_at.isoformat(),
                "backtest": bt_statuses.get(sub.id),
            }
            for sub in subs
        ]
