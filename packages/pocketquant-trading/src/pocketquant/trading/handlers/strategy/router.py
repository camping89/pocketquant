"""Strategy API routes aggregator."""

from fastapi import APIRouter

from pocketquant.trading.handlers.strategy.get_all.route import router as get_strategies_router
from pocketquant.trading.handlers.strategy.get_one.route import router as get_strategy_router
from pocketquant.trading.handlers.strategy.load.route import router as load_strategy_router
from pocketquant.trading.handlers.strategy.start.route import router as start_strategy_router
from pocketquant.trading.handlers.strategy.stop.route import router as stop_strategy_router

router = APIRouter(prefix="/strategies", tags=["strategies"])

# Include all operation-specific routers
router.include_router(get_strategies_router)
router.include_router(get_strategy_router)
router.include_router(load_strategy_router)
router.include_router(start_strategy_router)
router.include_router(stop_strategy_router)
