"""Strategy query service — read-side: list templates, subscriptions, positions, trades.

Query DTOs keep their original class names so callers that reference them
by name are unaffected by the handler→service migration.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)


@dataclass
class GetStrategiesQuery:
    pass


@dataclass
class GetStrategyQuery:
    strategy_code: str


class ListSymbolsQuery(BaseModel):
    strategy_code: str | None = None


class GetStrategyPositionsQuery(BaseModel):
    subscription_id: str


class GetStrategyTradesQuery(BaseModel):
    subscription_id: str
    limit: int = 100


class StrategyQueryService:
    """Read-side strategy operations — all reads from Mongo/RAM registries."""

    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        position_repository: PositionRepository,
    ) -> None:
        self._sub_repo = subscription_repository
        self._position_repo = position_repository

    async def get_all(self, query: GetStrategiesQuery) -> list[dict]:
        return [{"strategy_code": code} for code in STRATEGY_REGISTRY.keys()]

    async def get_one(self, query: GetStrategyQuery) -> dict | None:
        strategy_class = STRATEGY_REGISTRY.get(query.strategy_code)
        if strategy_class is None:
            return None
        return {
            "strategy_code": query.strategy_code,
            "class_name": strategy_class.__name__,
            "description": (strategy_class.__doc__ or "").strip().split("\n")[0]
            if strategy_class.__doc__
            else "",
        }

    async def list_symbols(self, query: ListSymbolsQuery) -> list[dict]:
        """List subscriptions filtered by strategy_code (or all if None).

        Run-state is sourced from the DB: ``actual_state`` is the reconcile
        loop's mirror of live engine state, so no RAM read is needed.
        ``is_running`` is derived (``actual_state == "running"``) for FE
        back-compat; ``desired_state`` exposes the transitional (converging) state.
        """
        if query.strategy_code is None:
            subs = await self._sub_repo.list_all()
        else:
            subs = await self._sub_repo.list_by_strategy_code(query.strategy_code)

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
            }
            for sub in subs
        ]

    async def get_positions(self, query: GetStrategyPositionsQuery) -> list[dict]:
        positions = await self._position_repo.find_open_by_subscription(query.subscription_id)
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

    async def get_trades(self, query: GetStrategyTradesQuery) -> list[dict]:
        """Return closed positions as the FE-consumed StrategyTrade shape.

        Closed positions are the canonical 'completed trade' record (entry +
        exit + realized PnL). Returning them avoids pairing raw fills client-side.
        """
        closed = await self._position_repo.find_closed_by_subscription(
            query.subscription_id, limit=query.limit
        )
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
