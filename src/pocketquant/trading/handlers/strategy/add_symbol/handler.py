"""AddSymbolHandler — persist a new Subscription (pure Mongo write)."""

from datetime import UTC, datetime

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.trading.handlers.strategy.add_symbol.command import AddSymbolCommand


@handles(AddSymbolCommand)
class AddSymbolHandler(Handler[AddSymbolCommand, dict]):
    """Persist a subscription — no RAM instance load.

    Pure Mongo write so the stateless bff can serve this without owning the
    engine. The app control-plane (reconcile loop) materializes the runtime
    instance within ≤1 tick. The tracked-symbol + registry checks stay: they
    fail fast (404) for the user instead of persisting a junk subscription that
    reconcile would only later reject.

    ``request.symbol`` must be composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        tracked_symbol_repository: TrackedSymbolRepository,
    ) -> None:
        self._sub_repo = subscription_repository
        self._tracked_repo = tracked_symbol_repository

    async def handle(self, request: AddSymbolCommand) -> dict:
        symbol = request.symbol.upper()
        if not await self._tracked_repo.exists(symbol):
            raise NotFoundError(
                f"Symbol '{symbol}' is not tracked. Admin must add it to tracked_symbols first.",
                error_code="SYMBOL_NOT_TRACKED",
            )

        if request.strategy_id not in STRATEGY_REGISTRY:
            raise NotFoundError(f"Strategy template '{request.strategy_id}' not found in registry.")

        sub_id = Subscription.deterministic_id(request.strategy_id, symbol, request.interval)

        # Add = subscribe only (desired_state="stopped"). The user starts it
        # explicitly via the start endpoint, which flips desired_state to running
        # and lets reconcile converge — no surprise auto-trading on add.
        sub = Subscription(
            id=sub_id,
            strategy_code=request.strategy_id,
            symbol=symbol,
            interval=Interval(request.interval),
            created_at=datetime.now(UTC),
            desired_state="stopped",
            actual_state="stopped",
        )
        await self._sub_repo.add(sub)
        return {
            "id": sub.id,
            "strategy_code": sub.strategy_code,
            "symbol": sub.symbol,
            "interval": sub.interval.value,
            "created_at": sub.created_at.isoformat(),
        }
