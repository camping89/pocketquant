"""Strategy command service — writes desired_state and subscription docs."""

from __future__ import annotations

from datetime import UTC, datetime

from pocketquant.core.common.exceptions import DomainError, NotFoundError
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.config import Settings
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)


class StrategyCommandService:
    """Write-side strategy operations — pure Mongo writes, no engine dependency.

    All mutations are declarative: desired_state is written and the app
    control-plane (reconcile loop) converges actual_state within one tick.
    """

    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        tracked_symbol_repository: TrackedSymbolRepository,
        settings: Settings,
    ) -> None:
        self._sub_repo = subscription_repository
        self._tracked_repo = tracked_symbol_repository
        self._settings = settings

    async def start(self, subscription_id: str) -> bool:
        """Set desired_state=running; reconcile converges actual within one tick.

        Declarative: returns before the strategy actually runs.
        """
        modified = await self._sub_repo.update_desired_state(subscription_id, "running")
        if modified == 0:
            raise NotFoundError(f"Subscription '{subscription_id}' not found.")
        return True

    async def stop(self, subscription_id: str) -> bool:
        """Set desired_state=stopped; reconcile converges actual within one tick.

        Declarative: returns before the strategy actually stops.
        """
        modified = await self._sub_repo.update_desired_state(subscription_id, "stopped")
        if modified == 0:
            raise NotFoundError(f"Subscription '{subscription_id}' not found.")
        return True

    async def add_symbol(
        self, strategy_id: str, symbol: str, interval: str, broker: str = "paper"
    ) -> dict:
        """Persist a new subscription — no RAM instance load.

        ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
        Pure Mongo write — the route handler never touches the engine; the
        reconcile loop materializes the instance. Fail-fast checks guard against
        junk subscriptions that reconcile would only later reject.
        """
        symbol = symbol.upper()
        if not await self._tracked_repo.exists(symbol):
            raise NotFoundError(
                f"Symbol '{symbol}' is not tracked. Admin must add it to tracked_symbols first.",
                error_code="SYMBOL_NOT_TRACKED",
            )

        if strategy_id not in STRATEGY_REGISTRY:
            raise NotFoundError(f"Strategy template '{strategy_id}' not found in registry.")

        if broker == "exness" and not self._settings.exness_live_trading:
            raise DomainError(
                "exness broker is disabled: EXNESS_LIVE_TRADING is false",
                error_code="BROKER_DISABLED",
            )

        # desired_state="stopped" — no surprise auto-trading on add.
        # The user starts it explicitly via the start endpoint.
        # Duplicate triples are rejected by the repo's compound unique index.
        sub = Subscription(
            id=generate_id(),
            strategy_code=strategy_id,
            symbol=symbol,
            interval=Interval(interval),
            created_at=datetime.now(UTC),
            desired_state="stopped",
            actual_state="stopped",
            broker=broker,
        )
        await self._sub_repo.add(sub)
        return {
            "id": str(sub.id),
            "strategy_code": sub.strategy_code,
            "symbol": sub.symbol,
            "interval": sub.interval.value,
            "created_at": sub.created_at.isoformat(),
            "broker": sub.broker,
        }

    async def remove_symbol(self, sub_id: str) -> int:
        """Cascade-delete a subscription's persisted state — pure Mongo write.

        No RAM unload: the app control-plane (reconcile orphan-unload) tears down
        the instance once the subscription doc is gone. Subscriptions no longer
        own any backtest state (forward-testing only), so only the sub doc drops.
        Returns the number of subscription docs deleted.
        """
        return await self._sub_repo.delete(sub_id)
