"""DeleteStrategyHandler — cascade-delete all state for a strategy template."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)
from pocketquant.core.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.trading.handlers.strategy.delete.command import DeleteStrategyCommand


@handles(DeleteStrategyCommand)
class DeleteStrategyHandler(Handler[DeleteStrategyCommand, None]):
    """Cascade-delete every persisted doc for a strategy template — pure Mongo.

    No RAM unload, no scheduler: the app control-plane (reconcile orphan-unload)
    tears down each instance once its subscription doc is gone, so the stateless
    bff can serve this. Order: drop queued requests + cached backtests first, then
    the subscriptions that key them.
    """

    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        backtest_repository: BacktestRepository,
        backtest_request_repository: BacktestRequestRepository,
    ) -> None:
        self._sub_repo = subscription_repository
        self._bt_repo = backtest_repository
        self._request_repo = backtest_request_repository

    async def handle(self, request: DeleteStrategyCommand) -> None:
        await self._request_repo.delete_by_strategy_code(request.strategy_id)
        await self._bt_repo.delete_by_strategy_code(request.strategy_id)
        await self._sub_repo.delete_by_strategy_code(request.strategy_id)
