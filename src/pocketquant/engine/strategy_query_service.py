"""Strategy query service — read-side: list templates, subscriptions, positions, trades.

Query DTOs keep their original class names so callers that reference them
by name are unaffected by the handler→service migration.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)

# ---------------------------------------------------------------------------
# Query DTOs
# ---------------------------------------------------------------------------


@dataclass
class GetStrategiesQuery:
    """List all registered strategy templates."""


@dataclass
class GetStrategyQuery:
    """Template metadata for a specific strategy code."""

    strategy_code: str


class ListSymbolsQuery(BaseModel):
    """List subscriptions with backtest status, optionally filtered by strategy template."""

    strategy_code: str | None = None


class GetStrategyPositionsQuery(BaseModel):
    """Open positions for a subscription instance."""

    subscription_id: str


class GetStrategyTradesQuery(BaseModel):
    """Completed trades (closed positions) for a subscription."""

    subscription_id: str
    limit: int = 100


class GetSubscriptionBacktestQuery(BaseModel):
    """Cached backtest result for a single subscription."""

    sub_id: str


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class StrategyQueryService:
    """Read-side strategy operations — all reads from Mongo/RAM registries."""

    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        backtest_repository: BacktestRepository,
        position_repository: PositionRepository,
    ) -> None:
        self._sub_repo = subscription_repository
        self._bt_repo = backtest_repository
        self._position_repo = position_repository

    async def get_all(self, query: GetStrategiesQuery) -> list[dict]:
        """List registered strategy templates from STRATEGY_REGISTRY."""
        return [{"strategy_code": code} for code in STRATEGY_REGISTRY.keys()]

    async def get_one(self, query: GetStrategyQuery) -> dict | None:
        """Return template metadata for a strategy code, or None if not registered."""
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

        sub_ids = [sub.id for sub in subs]
        bt_statuses = await self._bt_repo.get_subscription_statuses(sub_ids)

        return [
            {
                "id": sub.id,
                "strategy_code": sub.strategy_code,
                "symbol": sub.symbol,
                "interval": sub.interval.value,
                "created_at": sub.created_at.isoformat(),
                "desired_state": sub.desired_state,
                "actual_state": sub.actual_state,
                "is_running": sub.actual_state == "running",
                "backtest": bt_statuses.get(sub.id),
            }
            for sub in subs
        ]

    async def get_positions(self, query: GetStrategyPositionsQuery) -> list[dict]:
        """Return open positions (0 or more) as FE-friendly dicts."""
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
                "id": p.id,
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

    async def get_subscription_backtest(self, query: GetSubscriptionBacktestQuery) -> dict:
        """Return the backtest doc for the subscription, or 404 if never run.

        Uses find_doc_by_subscription() rather than find_by_subscription() so
        that status-only docs ('running', 'failed') that lack full BacktestResult
        fields are returned cleanly without deserialisation errors.
        """
        doc = await self._bt_repo.find_doc_by_subscription(query.sub_id)
        if doc is None:
            raise NotFoundError(
                f"No backtest found for subscription '{query.sub_id}'. "
                "Trigger a run via POST /strategies/{strategy_code}/run-all-backtests first."
            )
        return doc
