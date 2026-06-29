"""Backtest execution service — runs one ad-hoc backtest to completion.

The body of the ``asyncio.create_task`` the route spawns. Lives in the
``backtest`` layer (no fastapi import) so the route only allocates the run id,
persists the started doc, and hands off here.
"""

from __future__ import annotations

from typing import Any

from pocketquant.backtest.workers.backtest_dispatch import BacktestDispatchDeps, run_single
from pocketquant.core.common.logging import get_logger
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)

logger = get_logger(__name__)


class BacktestExecutionService:
    def __init__(self, deps: BacktestDispatchDeps, backtest_repository: BacktestRepository) -> None:
        self._deps = deps
        self._backtest_repo = backtest_repository

    async def execute_and_persist(self, run_id: str, config_payload: dict[str, Any]) -> None:
        """Run the engine for ``run_id`` and let it persist the run/orders/trades.

        The engine catches its own errors and RETURNS a ``failed`` result (it
        never re-raises), so a failed engine run is detected by inspecting the
        returned status — not by an exception. The ``except`` here only catches
        faults OUTSIDE the engine (e.g. a transient repo error around the call),
        and flips the started doc to ``failed`` so it can't stay stuck.
        """
        try:
            result = await run_single(self._deps, config_payload, run_id=run_id)
            if result.status == "failed":
                logger.warning(
                    "backtest_execution.engine_failed",
                    run_id=run_id,
                    error=result.error_message,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("backtest_execution.dispatch_failed", run_id=run_id, error=str(exc))
            await self._backtest_repo.mark_failed(run_id, str(exc)[:500])
