from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from pocketquant.core.common.exceptions import DomainError, NotFoundError
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.services import check_strategy_inputs
from pocketquant.core.domain.subscription import ManualAction, Subscription
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.safeguards_repository import (
    SafeguardsRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)


def _sub_dict(sub: Subscription) -> dict:
    return {
        "id": str(sub.id),
        "strategy_code": sub.strategy_code,
        "symbol": sub.symbol,
        "intervals": [i.value for i in sub.intervals],
        "parameters": dict(sub.parameters),
        "created_at": sub.created_at.isoformat(),
        "broker": sub.broker,
    }


def _running(sub_id: str) -> DomainError:
    return DomainError(
        f"Subscription '{sub_id}' must be stopped before it is edited.",
        error_code="SUBSCRIPTION_RUNNING",
        status_code=409,
    )


# Declarative: these methods write desired state and subscription docs and return
# before the engine acts; the reconcile loop converges within one tick.
class StrategyCommandService:
    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        tracked_symbol_repository: TrackedSymbolRepository,
        safeguards_repository: SafeguardsRepository,
        position_repository: PositionRepository,
        order_repository: OrderRepository,
    ) -> None:
        self._sub_repo = subscription_repository
        self._tracked_repo = tracked_symbol_repository
        self._safeguards_repo = safeguards_repository
        self._position_repo = position_repository
        self._order_repo = order_repository

    async def start(self, subscription_id: str) -> bool:
        modified = await self._sub_repo.update_desired_state(subscription_id, "running")
        if modified == 0:
            raise NotFoundError(f"Subscription '{subscription_id}' not found.")
        return True

    async def stop(self, subscription_id: str) -> bool:
        modified = await self._sub_repo.update_desired_state(subscription_id, "stopped")
        if modified == 0:
            raise NotFoundError(f"Subscription '{subscription_id}' not found.")
        return True

    # Fail-fast checks reject junk subscriptions the reconcile loop would only reject
    # later.
    async def add_symbol(
        self,
        strategy_id: str,
        symbol: str,
        intervals: list[str],
        parameters: dict,
        broker: str = "paper",
    ) -> dict:
        symbol = symbol.upper()
        if not await self._tracked_repo.exists(symbol):
            raise NotFoundError(
                f"Symbol '{symbol}' is not tracked. Admin must add it to tracked_symbols first.",
                error_code="SYMBOL_NOT_TRACKED",
            )

        check_strategy_inputs(strategy_id, intervals, parameters)

        # The trader's flag, not this process's: compose pins the api's own flag off.
        if broker == "exness" and not await self._safeguards_repo.load_live_trading():
            raise DomainError(
                "exness broker is disabled: the trader's EXNESS_LIVE_TRADING is false",
                error_code="BROKER_DISABLED",
            )

        # desired_state="stopped" — no surprise auto-trading on add.
        # The user starts it explicitly via the start endpoint.
        # A duplicate intervals key is rejected by the repo's unique index.
        sub = Subscription(
            id=generate_id(),
            strategy_code=strategy_id,
            symbol=symbol,
            intervals=tuple(Interval(i) for i in intervals),
            created_at=datetime.now(UTC),
            desired_state="stopped",
            actual_state="stopped",
            broker=broker,
            parameters=dict(parameters),
        )
        await self._sub_repo.add(sub)
        return _sub_dict(sub)

    async def edit(self, sub_id: str, intervals: list[str], parameters: dict) -> dict:
        sub = await self._sub_repo.get(sub_id)
        if sub is None:
            raise NotFoundError(f"Subscription '{sub_id}' not found.")
        if sub.desired_state != "stopped" or sub.actual_state != "stopped":
            raise _running(sub_id)
        # The reconcile loop unloads the stale instance to apply the edit, and unloading
        # drops a paper position, so the subscription must be flat with no resting order.
        pending = await self._order_repo.find_pending()
        if await self._position_repo.find_open_by_subscription(sub_id) or any(
            order.subscription_id == sub_id for order in pending
        ):
            raise DomainError(
                f"Subscription '{sub_id}' has an open position or a pending order.",
                error_code="SUBSCRIPTION_HAS_EXPOSURE",
                status_code=409,
            )
        check_strategy_inputs(sub.strategy_code, intervals, parameters)
        edited = replace(
            sub,
            intervals=tuple(Interval(i) for i in intervals),
            parameters=dict(parameters),
        )
        if await self._sub_repo.update_config(edited) == 0:
            raise _running(sub_id)
        return _sub_dict(edited)

    # The lease holder's reconcile tick attempts the action and clears it.
    async def request_action(self, sub_id: str, action: ManualAction) -> None:
        if await self._sub_repo.get(sub_id) is None:
            raise NotFoundError(f"Subscription '{sub_id}' not found.")
        if await self._sub_repo.request_action(sub_id, action) == 0:
            raise DomainError(
                "an action is already pending", error_code="ACTION_PENDING", status_code=409
            )

    async def remove_symbol(self, sub_id: str) -> int:
        return await self._sub_repo.delete(sub_id)
