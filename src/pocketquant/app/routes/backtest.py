"""Backtest API routes — single ad-hoc run + result reads (``/backtest`` prefix).

``POST /backtest/run`` allocates a run id, persists the ``started`` doc, then
spawns the engine as an in-process asyncio task (no queue). FE polls
``GET /backtest/{run_id}`` until ``finished``/``failed``.
"""

import asyncio
from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from pocketquant.backtest.backtest_command_service import (
    BacktestCommandService,
    RunBacktestCommand,
    SetVerdictCommand,
)
from pocketquant.backtest.backtest_execution_service import BacktestExecutionService
from pocketquant.backtest.backtest_query_service import (
    BacktestQueryService,
    EnqueueBacktestResponse,
    GetBacktestQuery,
    ListBacktestsQuery,
)
from pocketquant.backtest.backtest_stats_service import (
    BacktestStatsService,
    ListTradesQuery,
    TradeFilter,
    TradeSortDir,
    TradeSortKey,
)
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY

backtest_router = APIRouter(prefix="/backtest", tags=["backtest"], route_class=DishkaRoute)


class SetVerdictBody(BaseModel):
    verdict: str | None = Field(
        default=None, max_length=2000, description="Conclusion text; null clears it"
    )


@backtest_router.get("/strategies")
async def list_available_strategies() -> list[str]:
    return list(STRATEGY_REGISTRY.keys())


@backtest_router.post("/run", response_model=EnqueueBacktestResponse, status_code=202)
async def run_backtest(
    cmd: RunBacktestCommand,
    request: Request,
    cmd_svc: FromDishka[BacktestCommandService],
    execution_svc: FromDishka[BacktestExecutionService],
) -> dict:
    """Start a single backtest. Returns ``run_id`` (202); poll ``GET /backtest/{run_id}``.

    The engine runs in-process via ``asyncio.create_task`` — uncapped by design
    (the operator owns traffic). Concurrent runs share the live Mongo pool
    (``MONGODB_MAX_POOL_SIZE``, default 50), so a flood of large runs can starve
    live-trading order persistence; that trade-off is accepted, not guarded here.
    """
    run_id, config = await cmd_svc.run(cmd)
    tasks: set[asyncio.Task] = request.app.state.backtest_tasks
    task = asyncio.create_task(execution_svc.execute_and_persist(run_id, config))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return {"request_id": run_id}


@backtest_router.get("/{run_id}")
async def get_backtest(
    run_id: str,
    query_svc: FromDishka[BacktestQueryService],
) -> dict:
    result = await query_svc.get_result(GetBacktestQuery(run_id=run_id))
    return result.to_dict()


@backtest_router.patch("/{run_id}/verdict")
async def set_backtest_verdict(
    run_id: str,
    body: SetVerdictBody,
    cmd_svc: FromDishka[BacktestCommandService],
) -> dict:
    """Set (or clear) the human-readable verdict on a run. 404 if run unknown."""
    await cmd_svc.set_verdict(SetVerdictCommand(run_id=run_id, verdict=body.verdict))
    return {"run_id": run_id, "verdict": body.verdict}


@backtest_router.get("/{run_id}/equity")
async def get_backtest_equity(
    run_id: str,
    query_svc: FromDishka[BacktestQueryService],
) -> dict:
    result = await query_svc.get_result(GetBacktestQuery(run_id=run_id))
    return {
        "run_id": str(result.id),
        "equity_curve": [
            {"timestamp": p.timestamp.isoformat(), "equity": p.equity, "drawdown": p.drawdown}
            for p in result.equity_curve
        ],
    }


@backtest_router.get("/{run_id}/trades")
async def get_backtest_trades(
    run_id: str,
    stats_svc: FromDishka[BacktestStatsService],
    limit: int = 50,
    cursor: str | None = None,
    sort_key: TradeSortKey = TradeSortKey.entry_time,
    sort_dir: TradeSortDir = TradeSortDir.desc,
    filter: TradeFilter = TradeFilter.all,
) -> dict:
    """Keyset page of closed trades for a run, server-side filtered + sorted.

    ``cursor`` is the opaque token from the previous page's ``next_cursor``;
    omit it for the first page.
    """
    page = await stats_svc.list_trades_paged(
        ListTradesQuery(
            run_id=run_id,
            limit=limit,
            cursor=cursor,
            sort_key=sort_key,
            sort_dir=sort_dir,
            filter=filter,
        )
    )
    return page.model_dump()


@backtest_router.get("/{run_id}/trade-markers")
async def get_backtest_trade_markers(
    run_id: str,
    stats_svc: FromDishka[BacktestStatsService],
) -> dict:
    """Lite per-trade entry/exit/direction rows for the chart's entry/exit arrows."""
    markers = await stats_svc.list_markers(run_id)
    return {"run_id": run_id, "markers": [m.model_dump() for m in markers]}


@backtest_router.get("/{run_id}/stats")
async def get_backtest_stats(
    run_id: str,
    stats_svc: FromDishka[BacktestStatsService],
) -> dict:
    """Distribution + streak + profit-factor + drawdown analytics for a run."""
    stats = await stats_svc.get_stats(run_id)
    return stats.model_dump()


@backtest_router.get("/{run_id}/orders")
async def get_backtest_orders(
    run_id: str,
    query_svc: FromDishka[BacktestQueryService],
) -> dict:
    """Orders for a run with embedded fills + lifecycle events (DTO key ``order_id``)."""
    orders = await query_svc.list_orders(run_id)
    return {"run_id": run_id, "orders": orders}


@backtest_router.get("/strategy/{strategy_id}")
async def list_backtests(
    strategy_id: str,
    query_svc: FromDishka[BacktestQueryService],
    limit: int = 20,
    include_failed: bool = False,
    symbol: str | None = None,
    interval: str | None = None,
) -> list[dict[str, Any]]:
    """History for a strategy, optionally scoped to a composite symbol + interval.

    ``symbol`` is composite ``CODE:EXCHANGE`` (e.g. ``BTCUSDT:BINANCE``) — passing
    a bare code never matches a stored run.
    """
    results = await query_svc.list_results(
        ListBacktestsQuery(
            strategy_id=strategy_id,
            limit=limit,
            include_failed=include_failed,
            symbol=symbol,
            interval=interval,
        )
    )
    return [
        {
            "id": str(r.id),
            "strategy_code": r.strategy_code,
            "symbol": r.symbol,
            "interval": r.interval,
            "status": r.status,
            "metrics": r.metrics.to_dict(),
            "date_range": {
                "start": r.config_snapshot.get("start_date"),
                "end": r.config_snapshot.get("end_date"),
            },
            "verdict": r.verdict,
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat(),
            "parameters": r.parameters,
            "error_message": r.error_message,
        }
        for r in results
    ]
