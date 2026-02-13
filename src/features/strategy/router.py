"""Strategy API routes aggregator."""

from fastapi import APIRouter

from src.features.strategy.get_all.route import router as get_strategies_router
from src.features.strategy.get_one.route import router as get_strategy_router
from src.features.strategy.load.route import router as load_strategy_router
from src.features.strategy.start.route import router as start_strategy_router
from src.features.strategy.stop.route import router as stop_strategy_router

router = APIRouter(prefix="/strategies", tags=["strategies"])

# Include all operation-specific routers
router.include_router(get_strategies_router)
router.include_router(get_strategy_router)
router.include_router(load_strategy_router)
router.include_router(start_strategy_router)
router.include_router(stop_strategy_router)
