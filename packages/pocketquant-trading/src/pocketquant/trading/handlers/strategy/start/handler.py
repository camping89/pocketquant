"""Start strategy command handler — declarative: writes desired_state only."""

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.infrastructure.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.trading.handlers.strategy.start.command import StartStrategyCommand


@handles(StartStrategyCommand)
class StartStrategyHandler(Handler[StartStrategyCommand, bool]):
    """Set ``desired_state=running``; the reconcile loop starts the engine (≤1 tick).

    Declarative by design: this returns before the strategy actually runs. The
    reconcile loop converges actual_state toward desired within one interval, and
    the FE observes the catch-up via list_symbols. No direct engine call here —
    the handler↔runtime boundary is Mongo only.
    """

    def __init__(self, subscription_repository: SubscriptionRepository) -> None:
        self._sub_repo = subscription_repository

    async def handle(self, request: StartStrategyCommand) -> bool:
        modified = await self._sub_repo.update_desired_state(
            request.subscription_id, "running"
        )
        if modified == 0:
            raise NotFoundError(f"Subscription '{request.subscription_id}' not found.")
        return True
