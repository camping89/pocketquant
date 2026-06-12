"""Backtest query service — read-side: get result, list results, get optimization, poll request.

DTO class names are preserved from the handlers layer so call-sites that
reference them by name require no import-path changes beyond the module prefix.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.domain.backtest import BacktestResult, OptimizationResult
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)
from pocketquant.core.infra.persistence.repositories.optimization_repository import (
    OptimizationRepository,
)

# ---------------------------------------------------------------------------
# Query DTOs  (class names unchanged — public contract)
# ---------------------------------------------------------------------------


class GetBacktestQuery(BaseModel):
    """Query to get a specific backtest result by ID."""

    run_id: str


class ListBacktestsQuery(BaseModel):
    """Query to list backtest results for a strategy."""

    strategy_id: str
    limit: int = 20
    include_failed: bool = False


class GetOptimizationQuery(BaseModel):
    """Query to get a specific optimization result by ID."""

    optimization_id: str


# ---------------------------------------------------------------------------
# Response models  (OpenAPI components — class names and fields unchanged)
# ---------------------------------------------------------------------------


class EnqueueBacktestResponse(BaseModel):
    """Response after enqueuing a single backtest — FE polls for the result."""

    request_id: str


class BacktestRequestStatusResponse(BaseModel):
    """Poll response for a single backtest request.

    ``result`` carries the assembled FE payload (run_id/status/metrics/positions)
    once ``status == 'done'``; it is None while pending/running and on failure.
    """

    request_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


class OptimizationSummaryResponse(BaseModel):
    """Summary of optimization run."""

    id: str
    strategy_code: str
    status: str
    total_combinations: int
    completed_combinations: int
    failed_combinations: int
    target_metric: str
    best_parameters: dict[str, Any]
    best_metric_value: float


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class BacktestQueryService:
    """Read-side backtest operations — queries from Mongo collections."""

    def __init__(
        self,
        backtest_repository: BacktestRepository,
        backtest_request_repository: BacktestRequestRepository,
        optimization_repository: OptimizationRepository,
    ) -> None:
        self._backtest_repo = backtest_repository
        self._request_repo = backtest_request_repository
        self._optimization_repo = optimization_repository

    async def get_result(self, query: GetBacktestQuery) -> BacktestResult:
        """Return a backtest result by run_id, or raise 404."""
        result = await self._backtest_repo.get(query.run_id)
        if result is None:
            raise NotFoundError(f"Backtest not found: {query.run_id}")
        return result

    async def list_results(self, query: ListBacktestsQuery) -> list[BacktestResult]:
        """List backtest results for a strategy."""
        return await self._backtest_repo.list_by_strategy_code(
            strategy_code=query.strategy_id,
            limit=query.limit,
            include_failed=query.include_failed,
        )

    async def get_optimization(self, query: GetOptimizationQuery) -> OptimizationResult:
        """Return an optimization result by id, or raise 404."""
        result = await self._optimization_repo.get(query.optimization_id)
        if result is None:
            raise NotFoundError(f"Optimization not found: {query.optimization_id}")
        return result

    async def get_request_status(self, request_id: str) -> dict[str, Any]:
        """Return the poll payload for a single backtest request."""
        bt_request = await self._request_repo.get(request_id)
        if bt_request is None:
            raise NotFoundError(f"Backtest request not found: {request_id}")
        return {
            "request_id": str(bt_request.id),
            "status": bt_request.status,
            "result": bt_request.result,
            "error": bt_request.error,
        }
