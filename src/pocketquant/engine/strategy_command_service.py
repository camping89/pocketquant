"""Strategy command service — writes desired_state and cascade-deletes.

Command DTOs keep their original class names so callers that reference them
by name are unaffected by the handler→service migration.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)


class StartStrategyCommand(BaseModel):
    subscription_id: str


class StopStrategyCommand(BaseModel):
    subscription_id: str


class AddSymbolCommand(BaseModel):
    """Subscribe a strategy to a (symbol, interval) tuple.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    strategy_id: str
    symbol: str
    interval: str


class RemoveSymbolCommand(BaseModel):
    sub_id: str


class DeleteStrategyCommand(BaseModel):
    strategy_id: str


class StrategyCommandService:
    """Write-side strategy operations — pure Mongo writes, no engine dependency.

    All mutations are declarative: desired_state is written and the app
    control-plane (reconcile loop) converges actual_state within one tick.
    """

    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        backtest_repository: BacktestRepository,
        tracked_symbol_repository: TrackedSymbolRepository,
    ) -> None:
        self._sub_repo = subscription_repository
        self._bt_repo = backtest_repository
        self._tracked_repo = tracked_symbol_repository

    async def start(self, cmd: StartStrategyCommand) -> bool:
        """Set desired_state=running; reconcile converges actual within one tick.

        Declarative: returns before the strategy actually runs.
        """
        modified = await self._sub_repo.update_desired_state(cmd.subscription_id, "running")
        if modified == 0:
            raise NotFoundError(f"Subscription '{cmd.subscription_id}' not found.")
        return True

    async def stop(self, cmd: StopStrategyCommand) -> bool:
        """Set desired_state=stopped; reconcile converges actual within one tick.

        Declarative: returns before the strategy actually stops.
        """
        modified = await self._sub_repo.update_desired_state(cmd.subscription_id, "stopped")
        if modified == 0:
            raise NotFoundError(f"Subscription '{cmd.subscription_id}' not found.")
        return True

    async def add_symbol(self, cmd: AddSymbolCommand) -> dict:
        """Persist a new subscription — no RAM instance load.

        Pure Mongo write — the route handler never touches the engine; the
        reconcile loop materializes the instance. Fail-fast checks guard against
        junk subscriptions that reconcile would only later reject.
        """
        symbol = cmd.symbol.upper()
        if not await self._tracked_repo.exists(symbol):
            raise NotFoundError(
                f"Symbol '{symbol}' is not tracked. Admin must add it to tracked_symbols first.",
                error_code="SYMBOL_NOT_TRACKED",
            )

        if cmd.strategy_id not in STRATEGY_REGISTRY:
            raise NotFoundError(f"Strategy template '{cmd.strategy_id}' not found in registry.")

        # desired_state="stopped" — no surprise auto-trading on add.
        # The user starts it explicitly via the start endpoint.
        # Duplicate triples are rejected by the repo's compound unique index.
        sub = Subscription(
            id=generate_id(),
            strategy_code=cmd.strategy_id,
            symbol=symbol,
            interval=Interval(cmd.interval),
            created_at=datetime.now(UTC),
            desired_state="stopped",
            actual_state="stopped",
        )
        await self._sub_repo.add(sub)
        return {
            "id": str(sub.id),
            "strategy_code": sub.strategy_code,
            "symbol": sub.symbol,
            "interval": sub.interval.value,
            "created_at": sub.created_at.isoformat(),
        }

    async def remove_symbol(self, cmd: RemoveSymbolCommand) -> None:
        """Cascade-delete a subscription's persisted state — pure Mongo write.

        No RAM unload: the app control-plane (reconcile orphan-unload) tears down
        the instance once the subscription doc is gone. Subscriptions no longer
        own any backtest state (forward-testing only), so only the sub doc drops.
        """
        await self._sub_repo.delete(cmd.sub_id)

    async def delete_strategy(self, cmd: DeleteStrategyCommand) -> None:
        """Cascade-delete every persisted doc for a strategy template — pure Mongo.

        No RAM unload, no scheduler: the app control-plane (reconcile orphan-unload)
        tears down each instance once its subscription doc is gone. Ad-hoc backtest
        runs for this strategy are dropped too; then the subscriptions.
        """
        await self._bt_repo.delete_by_strategy_code(cmd.strategy_id)
        await self._sub_repo.delete_by_strategy_code(cmd.strategy_id)
