"""Backtest command service — write-side: start a single ad-hoc run.

DTO class names are preserved from the handlers layer so call-sites that
reference them by name require no import-path changes beyond the module prefix.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)


class RunBacktestCommand(BaseModel):
    """Command to execute a single backtest run.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
    """

    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str = Field(..., description="Composite symbol (e.g. BTCUSDT:BINANCE)")
    interval: str = Field(..., description="Bar interval (e.g. 5m, 1h)")
    start_date: datetime = Field(..., description="Backtest start datetime (minute precision)")
    end_date: datetime = Field(..., description="Backtest end datetime (minute precision)")
    initial_capital: float = Field(default=10_000.0, ge=100, description="Starting capital")
    slippage_bps: float = Field(default=10.0, ge=0, description="Slippage in basis points")
    commission_bps: float = Field(default=4.0, ge=0, description="Commission in basis points")
    parameters: dict[str, Any] | None = Field(default=None, description="Strategy parameters")


class SetVerdictCommand(BaseModel):
    """Command to set (or clear) the human-readable verdict on a finished run."""

    run_id: str = Field(..., description="Backtest run id")
    verdict: str | None = Field(
        default=None, max_length=2000, description="Conclusion text; null clears it"
    )


class BacktestCommandService:
    def __init__(self, backtest_repository: BacktestRepository) -> None:
        self._backtest_repo = backtest_repository

    async def run(self, cmd: RunBacktestCommand) -> tuple[str, dict[str, Any]]:
        """Allocate the run id, persist the ``started`` doc, return (id, config).

        The route spawns ``BacktestExecutionService.execute_and_persist`` against
        the returned id/config — the started doc lets FE poll immediately while
        the engine runs and overwrites this same id on finish/fail.
        """
        run_id = generate_id_str()
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
        await self._backtest_repo.save(BacktestResult.started(run_id, config))
        return run_id, config

    async def set_verdict(self, cmd: SetVerdictCommand) -> None:
        """Set the run's verdict; raise NotFoundError if the run does not exist."""
        matched = await self._backtest_repo.set_verdict(cmd.run_id, cmd.verdict)
        if not matched:
            raise NotFoundError(f"Backtest not found: {cmd.run_id}")
