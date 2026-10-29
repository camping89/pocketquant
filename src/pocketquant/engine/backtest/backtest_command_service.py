from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.time import coerce_utc, to_utc_iso
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)


class RunBacktestCommand(BaseModel):
    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str = Field(..., description="Composite symbol (e.g. BTCUSDT:BINANCE)")
    interval: str = Field(..., description="Bar interval (e.g. 5m, 1h)")
    start_date: datetime = Field(..., description="Backtest start datetime (minute precision)")
    end_date: datetime = Field(..., description="Backtest end datetime (minute precision)")
    initial_capital: float = Field(default=10_000.0, ge=100, description="Starting capital")
    slippage_bps: float = Field(default=0.5, ge=0, description="Slippage in basis points")
    commission_bps: float = Field(default=3.0, ge=0, description="Commission in basis points")
    spread: float = Field(
        default=0.0,
        ge=0,
        description=(
            "Constant spread in price units; ask = bid + spread, "
            "so BUY entries and SHORT exits fill at ask"
        ),
    )
    parameters: dict[str, Any] | None = Field(default=None, description="Strategy parameters")
    name: str | None = Field(default=None, max_length=200, description="Optional run label")

    @field_validator("start_date", "end_date", mode="after")
    @classmethod
    def _to_utc(cls, v: datetime) -> datetime:
        # Routes accept an ISO string that may carry no offset; anchor it to UTC
        # here so the run window means the same thing wherever it was submitted.
        return coerce_utc(v)  # type: ignore[return-value]


class BacktestCommandService:
    def __init__(self, backtest_repository: BacktestRepository) -> None:
        self._backtest_repo = backtest_repository

    # The started doc lets the frontend poll at once; the engine overwrites this same id
    # when the run finishes or fails.
    async def run(self, cmd: RunBacktestCommand) -> tuple[str, dict[str, Any]]:
        run_id = generate_id_str()
        config = {
            "strategy_code": cmd.strategy_id,
            "symbol": cmd.symbol,
            "interval": cmd.interval,
            "start_date": to_utc_iso(cmd.start_date),
            "end_date": to_utc_iso(cmd.end_date),
            "initial_capital": cmd.initial_capital,
            "slippage_bps": cmd.slippage_bps,
            "commission_bps": cmd.commission_bps,
            "spread": cmd.spread,
            "parameters": cmd.parameters or {},
            "name": cmd.name,
        }
        await self._backtest_repo.save(BacktestResult.started(run_id, config))
        return run_id, config

    async def set_verdict(self, run_id: str, verdict: str | None) -> None:
        matched = await self._backtest_repo.set_verdict(run_id, verdict)
        if not matched:
            raise NotFoundError(f"Backtest not found: {run_id}")

    async def set_name(self, run_id: str, name: str | None) -> None:
        matched = await self._backtest_repo.set_name(run_id, name)
        if not matched:
            raise NotFoundError(f"Backtest not found: {run_id}")
