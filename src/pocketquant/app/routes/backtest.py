import asyncio
from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from pocketquant.core.common.time import to_utc_iso
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.engine.backtest.backtest_command_service import (
    BacktestCommandService,
    RunBacktestCommand,
)
from pocketquant.engine.backtest.backtest_execution_service import BacktestExecutionService
from pocketquant.engine.backtest.backtest_query_service import (
    BacktestQueryService,
    EnqueueBacktestResponse,
    ListBacktestsQuery,
)
from pocketquant.engine.backtest.backtest_stats_service import (
    BacktestStatsService,
    ListTradesQuery,
    TradeFilter,
    TradeSortDir,
    TradeSortKey,
)

backtest_router = APIRouter(prefix="/backtest", tags=["backtest"], route_class=DishkaRoute)


class SetVerdictBody(BaseModel):
    verdict: str | None = Field(
        default=None, max_length=2000, description="Conclusion text; null clears it"
    )


class SetNameBody(BaseModel):
    name: str | None = Field(default=None, max_length=200, description="Run label; null clears it")


@backtest_router.get("/strategies")
async def list_available_strategies() -> list[str]:
    return list(STRATEGY_REGISTRY.keys())


# Uncapped by design: concurrent runs share the live Mongo pool, so a flood of
# large runs can starve live order persistence. That trade-off is accepted.
@backtest_router.post("/run", response_model=EnqueueBacktestResponse, status_code=202)
async def run_backtest(
    cmd: RunBacktestCommand,
    request: Request,
    cmd_svc: FromDishka[BacktestCommandService],
    execution_svc: FromDishka[BacktestExecutionService],
) -> dict:
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
    result = await query_svc.get_result(run_id)
    return result.to_dict()


@backtest_router.patch("/{run_id}/verdict")
async def set_backtest_verdict(
    run_id: str,
    body: SetVerdictBody,
    cmd_svc: FromDishka[BacktestCommandService],
) -> dict:
    await cmd_svc.set_verdict(run_id, body.verdict)
    return {"run_id": run_id, "verdict": body.verdict}


@backtest_router.patch("/{run_id}/name")
async def set_backtest_name(
    run_id: str,
    body: SetNameBody,
    cmd_svc: FromDishka[BacktestCommandService],
) -> dict:
    await cmd_svc.set_name(run_id, body.name)
    return {"run_id": run_id, "name": body.name}


@backtest_router.get("/{run_id}/equity")
async def get_backtest_equity(
    run_id: str,
    query_svc: FromDishka[BacktestQueryService],
) -> dict:
    result = await query_svc.get_result(run_id)
    return {
        "run_id": str(result.id),
        "equity_curve": [
            {"timestamp": to_utc_iso(p.timestamp), "equity": p.equity, "drawdown": p.drawdown}
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
    markers = await stats_svc.list_markers(run_id)
    return {"run_id": run_id, "markers": [m.model_dump() for m in markers]}


@backtest_router.get("/{run_id}/stats")
async def get_backtest_stats(
    run_id: str,
    stats_svc: FromDishka[BacktestStatsService],
) -> dict:
    stats = await stats_svc.get_stats(run_id)
    return stats.model_dump()


@backtest_router.get("/{run_id}/orders")
async def get_backtest_orders(
    run_id: str,
    query_svc: FromDishka[BacktestQueryService],
) -> dict:
    orders = await query_svc.list_orders(run_id)
    return {"run_id": run_id, "orders": orders}


# symbol is composite CODE:EXCHANGE; a bare code never matches a stored run.
@backtest_router.get("/strategy/{strategy_id}")
async def list_backtests(
    strategy_id: str,
    query_svc: FromDishka[BacktestQueryService],
    limit: int = 20,
    include_failed: bool = False,
    symbol: str | None = None,
    interval: str | None = None,
) -> list[dict[str, Any]]:
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
            "name": r.name,
            "symbol": r.symbol,
            "interval": r.interval,
            "status": r.status,
            "metrics": r.metrics.to_dict(),
            "date_range": {
                "start": r.config_snapshot.get("start_date"),
                "end": r.config_snapshot.get("end_date"),
            },
            "verdict": r.verdict,
            "started_at": to_utc_iso(r.started_at),
            "completed_at": to_utc_iso(r.completed_at),
            "parameters": r.parameters,
            "error_message": r.error_message,
        }
        for r in results
    ]
