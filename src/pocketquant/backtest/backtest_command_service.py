"""Backtest command service — write-side: enqueue run, optimize, run-all.

DTO class names are preserved from the handlers layer so call-sites that
reference them by name require no import-path changes beyond the module prefix.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field

from pocketquant.backtest.optimization.grid_optimization_app_service import (
    GridOptimizationAppService,
)
from pocketquant.backtest.optimization.models.optimization_config import OptimizationConfig
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.backtest import OptimizationResult
from pocketquant.core.domain.backtest.request import BacktestRequest
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.optimization_repository import (
    OptimizationRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)


class RunBacktestCommand(BaseModel):
    """Command to execute a single backtest run.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str = Field(..., description="Composite symbol (e.g. BTCUSDT:BINANCE)")
    interval: str = Field(..., description="Bar interval (e.g. 5m, 1h)")
    start_date: date = Field(..., description="Backtest start date")
    end_date: date = Field(..., description="Backtest end date")
    initial_capital: float = Field(default=10_000.0, ge=100, description="Starting capital")
    slippage_bps: float = Field(default=10.0, ge=0, description="Slippage in basis points")
    commission_bps: float = Field(default=10.0, ge=0, description="Commission in basis points")
    parameters: dict[str, Any] | None = Field(default=None, description="Strategy parameters")


class RunOptimizationCommand(BaseModel):
    """Command to run grid optimization across parameter combinations.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str = Field(..., description="Composite symbol (e.g. BTCUSDT:BINANCE)")
    interval: str = Field(..., description="Bar interval")
    start_date: date = Field(..., description="Backtest start date")
    end_date: date = Field(..., description="Backtest end date")
    parameter_grid: dict[str, list[Any]] = Field(
        ..., description="Parameter grid (e.g., {'ma_fast': [5,10,20]})"
    )
    initial_capital: float = Field(default=10_000.0, ge=100)
    slippage_bps: float = Field(default=10.0, ge=0)
    commission_bps: float = Field(default=10.0, ge=0)
    target_metric: str = Field(default="sharpe_ratio", description="Metric to optimize")
    max_workers: int = Field(default=4, ge=1, le=16, description="Max concurrent backtests")


class RunAllBacktestsCommand(BaseModel):
    strategy_id: str


class BacktestCommandService:
    def __init__(
        self,
        backtest_request_repository: BacktestRequestRepository,
        subscription_repository: SubscriptionRepository,
        backtest_repository: BacktestRepository,
        bar_repository: BarRepository,
        optimization_repository: OptimizationRepository,
    ) -> None:
        self._request_repo = backtest_request_repository
        self._sub_repo = subscription_repository
        self._backtest_repo = backtest_repository
        self._bar_repo = bar_repository
        self._optimization_repo = optimization_repository

    async def run(self, cmd: RunBacktestCommand) -> dict[str, str]:
        config = {
            "strategy_code": cmd.strategy_id,
            "symbol": cmd.symbol,
            "interval": cmd.interval,
            "start_date": cmd.start_date.isoformat(),
            "end_date": cmd.end_date.isoformat(),
            "initial_capital": cmd.initial_capital,
            "slippage_bps": cmd.slippage_bps,
            "commission_bps": cmd.commission_bps,
            "parameters": cmd.parameters or {},
        }
        bt_request = BacktestRequest(
            id=generate_id(),
            kind="single",
            status="pending",
            requested_at=datetime.now(UTC),
            strategy_code=cmd.strategy_id,
            config=config,
        )
        request_id = await self._request_repo.enqueue(bt_request)
        return {"request_id": request_id}

    async def optimize(self, cmd: RunOptimizationCommand) -> OptimizationResult:
        config = OptimizationConfig(
            strategy_code=cmd.strategy_id,
            symbol=cmd.symbol,
            interval=cmd.interval,
            start_date=cmd.start_date,
            end_date=cmd.end_date,
            parameter_grid=cmd.parameter_grid,
            initial_capital=cmd.initial_capital,
            slippage_bps=cmd.slippage_bps,
            commission_bps=cmd.commission_bps,
            target_metric=cmd.target_metric,
            max_workers=cmd.max_workers,
        )
        optimizer = GridOptimizationAppService(
            backtest_repository=self._backtest_repo,
            bar_repository=self._bar_repo,
        )
        result = await optimizer.optimize(config)
        await self._optimization_repo.save(result)
        return result

    async def run_all(self, cmd: RunAllBacktestsCommand) -> dict[str, list[str]]:
        """Enqueue one backtest request per subscription for a strategy template.

        Dedup lives in the repo's (sub_id, status=pending) upsert backed by a
        partial unique index, so concurrent fan-outs collapse to a single
        pending request per subscription — preserves the invariant the old
        APScheduler ``replace_existing`` provided. The persisted id (which may
        belong to an already-pending doc) is what FE receives.
        """
        subs = await self._sub_repo.list_by_strategy_code(cmd.strategy_id)
        if not subs:
            raise NotFoundError(
                f"No subscriptions found for strategy '{cmd.strategy_id}'. "
                "Add symbols via POST /{strategy_id}/symbols first."
            )

        # FE reads `job_ids`; keep the key name so no FE change is required.
        job_ids: list[str] = []
        for sub in subs:
            bt_request = BacktestRequest(
                id=generate_id(),
                kind="subscription",
                status="pending",
                requested_at=datetime.now(UTC),
                sub_id=str(sub.id),
                strategy_code=sub.strategy_code,
            )
            persisted_id = await self._request_repo.enqueue(bt_request)
            job_ids.append(persisted_id)

        return {"job_ids": job_ids}
