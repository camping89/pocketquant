"""BacktestRequestWorker — poll-loop that drains the backtest_requests queue.

Mirrors StrategyReconcileService.run: a ``while True`` loop with a per-tick
backstop, claiming one request at a time via the repo's atomic
``claim_next``. Runs on the headless ``pocketquant-app`` only — the stateless
``pocketquant-bff`` merely INSERTs requests.

The worker owns ALL backtest compute (single + subscription), replacing the
removed APScheduler ``bt:*`` one-off jobs.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pocketquant.backtest.workers.backtest_dispatch import (
    BacktestDispatchDeps,
    run_single,
    run_subscription,
)
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.domain.backtest.request import BacktestRequest
from pocketquant.infrastructure.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)
from pocketquant.infrastructure.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)

logger = get_logger(__name__)


class BacktestRequestWorker:
    """Drains ``backtest_requests`` — claim → dispatch by kind → write status.

    Args:
        request_repo: Queue persistence (atomic claim + status writes).
        deps: Engine dependencies shared by single + subscription dispatch.
        interval_s: Seconds between empty-queue polls (default 2.0).
    """

    def __init__(
        self,
        request_repo: BacktestRequestRepository,
        deps: BacktestDispatchDeps,
        interval_s: float = 2.0,
    ) -> None:
        self._request_repo = request_repo
        self._deps = deps
        self._interval_s = interval_s

    async def run(self) -> None:
        """Poll loop. Runs until cancelled by lifespan shutdown."""
        logger.info("backtest_worker.started", interval_s=self._interval_s)

        while True:
            try:
                await self._request_repo.reclaim_stale_running()
                claimed = await self._drain_once()
            except asyncio.CancelledError:
                logger.info("backtest_worker.cancelled")
                raise
            except Exception as exc:
                # Per-tick backstop — never crash the app; retry next tick.
                logger.error("backtest_worker.tick_failed", error=str(exc))
                claimed = False

            # When a request was processed, immediately poll again (queue may be
            # non-empty); only sleep when the queue ran dry.
            if not claimed:
                await asyncio.sleep(self._interval_s)

    async def _drain_once(self) -> bool:
        """Claim and dispatch one request. Returns True if one was processed.

        Per-request isolation: a single failed request is marked failed and the
        loop continues — it never blocks the next request.
        """
        request = await self._request_repo.claim_next()
        if request is None:
            return False

        try:
            await self._dispatch(request)
        except Exception as exc:
            logger.error(
                "backtest_worker.request_failed",
                request_id=request.id,
                kind=request.kind,
                error=str(exc),
            )
            await self._request_repo.mark_failed(request.id, str(exc))
        return True

    async def _dispatch(self, request: BacktestRequest) -> None:
        if request.kind == "subscription":
            if request.sub_id is None:
                raise ValueError("subscription request missing sub_id")
            await run_subscription(self._deps, request.sub_id)
            await self._request_repo.mark_done(request.id)
            return

        if request.kind == "single":
            if request.config is None:
                raise ValueError("single request missing config")
            result = await run_single(self._deps, request.config)
            fe_result = await self._assemble_single_response(result)
            await self._request_repo.mark_done(request.id, result=fe_result)
            return

        raise ValueError(f"unknown backtest request kind: {request.kind}")

    async def _assemble_single_response(self, result: BacktestResult) -> dict[str, Any]:
        """Build the FE-facing response embedded in the request doc.

        Same shape the synchronous ``POST /backtest/run`` route returned:
        run_id + status + metrics + unified positions (closed round-trip Trades
        from ``backtest_trades`` plus still-open lots from the run doc). FE renders
        this unchanged when polling ``/backtest/requests/{id}``.
        """
        positions: list[dict[str, Any]] = []
        if result.status == "completed":
            trade_repo: BacktestTradeRepository = self._deps.trade_repo
            closed = await trade_repo.list_by_run(result.id)
            for t in closed:
                positions.append(
                    {
                        "entry_price": t.entry_price,
                        "entry_time": t.entry_time.isoformat(),
                        "exit_price": t.exit_price,
                        "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                        "quantity": t.quantity,
                        "sl_price": t.sl_price,
                        "tp_price": t.tp_price,
                        "pnl": t.pnl,
                        "commission": t.commission,
                    }
                )
            for ol in result.open_positions:
                positions.append(
                    {
                        "entry_price": ol.entry_price,
                        "entry_time": ol.entry_time.isoformat(),
                        "exit_price": None,
                        "exit_time": None,
                        "quantity": ol.quantity,
                        "sl_price": ol.sl_price,
                        "tp_price": ol.tp_price,
                        "pnl": 0.0,
                        "commission": ol.entry_commission_portion,
                    }
                )

        return {
            "run_id": result.id,
            "status": result.status,
            "metrics": result.metrics.to_dict() if result.status == "completed" else None,
            "positions": positions,
        }
