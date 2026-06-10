"""Backtest API routes - REST endpoints for backtest execution and results."""

from fastapi import APIRouter

from pocketquant.backtest.handlers import get_optimization, get_result, list_results, optimize, run
from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/strategies")
async def list_available_strategies() -> list[str]:
    """Return strategy IDs available for backtesting."""
    return list(STRATEGY_REGISTRY.keys())


# Include sub-routers (after static routes to avoid /{run_id} catching /strategies)
router.include_router(run.router)
router.include_router(optimize.router)
router.include_router(get_result.router)
router.include_router(get_optimization.router)
router.include_router(list_results.router)
