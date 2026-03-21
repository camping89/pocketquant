"""Backtest API routes - REST endpoints for backtest execution and results."""

from fastapi import APIRouter
from pocketquant.backtest.handlers import get_optimization, get_result, list_results, optimize, run

router = APIRouter(prefix="/backtest", tags=["backtest"])

# Include sub-routers from each operation
router.include_router(run.router)
router.include_router(optimize.router)
router.include_router(get_result.router)
router.include_router(get_optimization.router)
router.include_router(list_results.router)
