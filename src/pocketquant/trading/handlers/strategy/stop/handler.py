"""Stop strategy command handler — declarative: writes desired_state only."""

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.trading.handlers.strategy.stop.command import StopStrategyCommand


@handles(StopStrategyCommand)
class StopStrategyHandler(Handler[StopStrategyCommand, bool]):
    """Set ``desired_state=stopped``; the reconcile loop stops the engine (≤1 tick).

    Declarative: returns before the strategy actually stops. The reconcile loop
    converges actual_state within one interval. No direct engine call.
    """

    def __init__(self, subscription_repository: SubscriptionRepository) -> None:
        self._sub_repo = subscription_repository

    async def handle(self, request: StopStrategyCommand) -> bool:
        modified = await self._sub_repo.update_desired_state(request.subscription_id, "stopped")
        if modified == 0:
            raise NotFoundError(f"Subscription '{request.subscription_id}' not found.")
        return True
