"""Strategy API routes aggregator."""

from fastapi import APIRouter
from pocketquant.trading.handlers.strategy.add_symbol.route import router as add_symbol_router
from pocketquant.trading.handlers.strategy.delete.route import router as delete_strategy_router
from pocketquant.trading.handlers.strategy.get_all.route import router as get_strategies_router
from pocketquant.trading.handlers.strategy.get_one.route import router as get_strategy_router
from pocketquant.trading.handlers.strategy.get_subscription_backtest.route import (
    router as get_subscription_backtest_router,
)
from pocketquant.trading.handlers.strategy.list_symbols.route import router as list_symbols_router
from pocketquant.trading.handlers.strategy.load.route import router as load_strategy_router
from pocketquant.trading.handlers.strategy.remove_symbol.route import (
    router as remove_symbol_router,
)
from pocketquant.trading.handlers.strategy.run_all_backtests.route import (
    router as run_all_backtests_router,
)
from pocketquant.trading.handlers.strategy.start.route import router as start_strategy_router
from pocketquant.trading.handlers.strategy.stop.route import router as stop_strategy_router

router = APIRouter(prefix="/strategies", tags=["strategies"])

# Existing operation routers
router.include_router(get_strategies_router)
router.include_router(get_strategy_router)
router.include_router(load_strategy_router)
router.include_router(start_strategy_router)
router.include_router(stop_strategy_router)

# Subscription & backtest routers (Phase 2)
router.include_router(add_symbol_router)
router.include_router(list_symbols_router)
router.include_router(remove_symbol_router)
router.include_router(run_all_backtests_router)
router.include_router(get_subscription_backtest_router)
router.include_router(delete_strategy_router)
