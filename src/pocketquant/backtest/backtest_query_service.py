"""Backtest query service — read-side: get run, list runs, list trades.

DTO class names are preserved from the handlers layer so call-sites that
reference them by name require no import-path changes beyond the module prefix.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)


class GetBacktestQuery(BaseModel):
    run_id: str


class ListBacktestsQuery(BaseModel):
    strategy_id: str
    limit: int = 20
    include_failed: bool = False


class EnqueueBacktestResponse(BaseModel):
    request_id: str


class BacktestQueryService:
    """Read-side backtest operations — queries from Mongo collections."""

    def __init__(
        self,
        backtest_repository: BacktestRepository,
        backtest_trade_repository: BacktestTradeRepository,
    ) -> None:
        self._backtest_repo = backtest_repository
        self._trade_repo = backtest_trade_repository

    async def get_result(self, query: GetBacktestQuery) -> BacktestResult:
        result = await self._backtest_repo.get(query.run_id)
        if result is None:
            raise NotFoundError(f"Backtest not found: {query.run_id}")
        return result

    async def list_trades(self, run_id: str) -> list[dict[str, Any]]:
        """Closed round-trip trades for a run, shaped for the result view."""
        trades = await self._trade_repo.list_by_run(run_id)
        return [
            {
                "trade_id": str(t.trade_id),
                "direction": t.direction,
                "entry_price": t.entry_price,
                "entry_time": t.entry_time.isoformat(),
                "exit_price": t.exit_price,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "quantity": t.quantity,
                "sl_price": t.sl_price,
                "tp_price": t.tp_price,
                "pnl": t.pnl,
                "commission": t.commission,
                "duration_seconds": t.duration_seconds,
            }
            for t in trades
        ]

    async def list_results(self, query: ListBacktestsQuery) -> list[BacktestResult]:
        return await self._backtest_repo.list_by_strategy_code(
            strategy_code=query.strategy_id,
            limit=query.limit,
            include_failed=query.include_failed,
        )
