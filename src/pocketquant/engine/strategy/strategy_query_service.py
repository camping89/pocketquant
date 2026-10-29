from __future__ import annotations

from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)


class StrategyQueryService:
    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        position_repository: PositionRepository,
    ) -> None:
        self._sub_repo = subscription_repository
        self._position_repo = position_repository

    async def get_all(self) -> list[dict]:
        return [{"strategy_code": code} for code in STRATEGY_REGISTRY.keys()]

    async def get_one(self, strategy_code: str) -> dict | None:
        strategy_class = STRATEGY_REGISTRY.get(strategy_code)
        if strategy_class is None:
            return None
        return {
            "strategy_code": strategy_code,
            "class_name": strategy_class.__name__,
        }

    # actual_state is the reconcile loop's mirror of live engine state, so no RAM read.
    # is_running is derived for FE back-compat.
    async def list_symbols(self, strategy_code: str | None = None) -> list[dict]:
        if strategy_code is None:
            subs = await self._sub_repo.list_all()
        else:
            subs = await self._sub_repo.list_by_strategy_code(strategy_code)

        if not subs:
            return []

        return [
            {
                "id": str(sub.id),
                "strategy_code": sub.strategy_code,
                "symbol": sub.symbol,
                "interval": sub.interval.value,
                "created_at": sub.created_at.isoformat(),
                "desired_state": sub.desired_state,
                "actual_state": sub.actual_state,
                "is_running": sub.actual_state == "running",
                "broker": sub.broker,
            }
            for sub in subs
        ]

    async def get_positions(self, subscription_id: str) -> list[dict]:
        positions = await self._position_repo.find_open_by_subscription(subscription_id)
        return [
            {
                "symbol": p.symbol,
                "direction": p.side.value.upper(),
                "entry_price": p.entry_price,
                "quantity": p.quantity,
                "unrealized_pnl": p.unrealized_pnl,
                "entry_time": p.opened_at.isoformat(),
                "sl_price": p.sl_price,
                "tp_price": p.tp_price,
            }
            for p in positions
        ]

    # Closed positions are the canonical completed trade, so the FE never pairs raw fills.
    async def get_trades(self, subscription_id: str, limit: int = 100) -> list[dict]:
        closed = await self._position_repo.find_closed_by_subscription(subscription_id, limit=limit)
        return [
            {
                "id": str(p.id),
                "direction": p.side.value.upper(),
                "entry_price": p.entry_price,
                # Position close sets current_price = exit_price.
                "exit_price": p.current_price,
                "entry_time": p.opened_at.isoformat(),
                "exit_time": p.closed_at.isoformat() if p.closed_at else None,
                "pnl": p.realized_pnl,
                "quantity": p.quantity,
            }
            for p in closed
        ]
