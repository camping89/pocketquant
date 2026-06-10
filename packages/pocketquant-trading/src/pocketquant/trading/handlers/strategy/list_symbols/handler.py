"""ListSubscriptionsHandler — subscriptions enriched with backtest status + run-state."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.trading.handlers.strategy.list_symbols.query import ListSymbolsQuery


@handles(ListSymbolsQuery)
class ListSymbolsHandler(Handler[ListSymbolsQuery, list]):
    """Handle ListSymbolsQuery — join subscriptions with backtest status + run-state."""

    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        backtest_repository: BacktestRepository,
    ) -> None:
        self._sub_repo = subscription_repository
        self._bt_repo = backtest_repository

    async def handle(self, request: ListSymbolsQuery) -> list:
        """List subscriptions filtered by strategy_code (or all if None).

        Run-state is sourced from the DB: ``actual_state`` is the reconcile loop's
        mirror of live engine state, so no RAM read is needed. ``is_running`` is
        derived (``actual_state == "running"``) for FE back-compat; ``desired_state``
        is exposed so the FE can render the transitional (converging) state.
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
                "desired_state": sub.desired_state,
                "actual_state": sub.actual_state,
                "is_running": sub.actual_state == "running",
                "backtest": bt_statuses.get(sub.id),
            }
            for sub in subs
        ]
