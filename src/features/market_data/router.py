"""Market data router - aggregates all market data sub-feature routers."""

from fastapi import APIRouter

from src.features.market_data.list_symbols.route import router as list_symbols_router
from src.features.market_data.ohlcv.router import router as ohlcv_router
from src.features.market_data.status.router import router as status_router
from src.features.market_data.sync.router import router as sync_router

router = APIRouter(prefix="/market-data", tags=["Market Data"])

# Include sub-feature routers
router.include_router(sync_router)
router.include_router(ohlcv_router)
router.include_router(status_router)
router.include_router(list_symbols_router)
