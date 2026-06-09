"""RemoveSymbolHandler — delete subscription + cached backtest + queued requests."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.infrastructure.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.infrastructure.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)
from pocketquant.infrastructure.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.trading.handlers.strategy.remove_symbol.command import RemoveSymbolCommand


@handles(RemoveSymbolCommand)
class RemoveSymbolHandler(Handler[RemoveSymbolCommand, None]):
    """Cascade-delete a subscription's persisted state — pure Mongo write.

    No RAM unload, no scheduler: the app control-plane (reconcile orphan-unload)
    tears down the instance once the subscription doc is gone, so the stateless
    bff can serve this. Queued backtest requests are dropped too, preventing the
    worker from running work for a removed subscription.
    """

    def __init__(
        self,
        backtest_repository: BacktestRepository,
        backtest_request_repository: BacktestRequestRepository,
        subscription_repository: SubscriptionRepository,
    ) -> None:
        self._bt_repo = backtest_repository
        self._request_repo = backtest_request_repository
        self._sub_repo = subscription_repository

    async def handle(self, request: RemoveSymbolCommand) -> None:
        await self._request_repo.delete_by_subscription(request.sub_id)
        await self._bt_repo.delete_by_subscription(request.sub_id)
        await self._sub_repo.delete(request.sub_id)
