from __future__ import annotations

from pocketquant.core.common.constants import CACHE_KEY_STRATEGY_SNAPSHOT
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository
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
        order_repository: OrderRepository,
        cache: Cache,
    ) -> None:
        self._sub_repo = subscription_repository
        self._position_repo = position_repository
        self._order_repo = order_repository
        self._cache = cache

    async def get_all(self) -> list[dict]:
        return [{"strategy_code": code} for code in STRATEGY_REGISTRY.keys()]

    async def get_one(self, strategy_code: str) -> dict | None:
        strategy_class = STRATEGY_REGISTRY.get(strategy_code)
        if strategy_class is None:
            return None
        return {
            "strategy_code": strategy_code,
            "class_name": strategy_class.__name__,
            "parameters": dict(strategy_class.DEFAULTS),
        }

    # actual_state is the reconcile loop's mirror of live engine state, so no RAM read.
    # is_running is derived for FE back-compat. One positions read and one Redis read cover
    # every row, so the list costs no request per subscription.
    async def list_symbols(self, strategy_code: str | None = None) -> list[dict]:
        if strategy_code is None:
            subs = await self._sub_repo.list_all()
        else:
            subs = await self._sub_repo.list_by_strategy_code(strategy_code)

        if not subs:
            return []

        positions = {
            p.subscription_id: {
                "direction": p.side.value.upper(),
                "entry_price": p.entry_price,
                "quantity": p.quantity,
                "sl_price": p.sl_price,
                "tp_price": p.tp_price,
                "unrealized_pnl": p.unrealized_pnl,
            }
            for p in await self._position_repo.find_open()
        }
        rings = await self._cache.mget(
            [CACHE_KEY_STRATEGY_SNAPSHOT.format(subscription_id=str(sub.id)) for sub in subs]
        )
        return [
            {
                "id": str(sub.id),
                "strategy_code": sub.strategy_code,
                "symbol": sub.symbol,
                "intervals": [i.value for i in sub.intervals],
                "parameters": dict(sub.parameters),
                "created_at": sub.created_at.isoformat(),
                "desired_state": sub.desired_state,
                "actual_state": sub.actual_state,
                "is_running": sub.actual_state == "running",
                "broker": sub.broker,
                "position": positions.get(str(sub.id)),
                "snapshot": ring[-1] if ring else None,
                "manual_action": sub.manual_action,
                "manual_action_outcome": sub.manual_action_outcome,
            }
            for sub, ring in zip(subs, rings, strict=True)
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

    async def get_orders(self, subscription_id: str, limit: int) -> list[dict]:
        orders = await self._order_repo.list_by_subscription(subscription_id, limit)
        return [
            {
                "id": str(o.id),
                "side": o.side.value,
                "order_type": o.order_type.value,
                "status": o.status.value,
                "quantity": o.quantity,
                "price": o.price,
                "stop_price": o.stop_price,
                "sl_price": o.sl_price,
                "tp_price": o.tp_price,
                "filled_price": o.filled_price,
                "created_at": o.created_at.isoformat(),
                "updated_at": o.updated_at.isoformat(),
            }
            for o in orders
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
