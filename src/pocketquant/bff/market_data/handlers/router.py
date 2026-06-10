"""Market data router — aggregates all market data sub-feature routers."""

from fastapi import APIRouter

from pocketquant.bff.market_data.handlers.integrity.route import router as integrity_router
from pocketquant.bff.market_data.handlers.list_symbols.route import router as list_symbols_router
from pocketquant.bff.market_data.handlers.ohlcv.router import router as ohlcv_router
from pocketquant.bff.market_data.handlers.status.router import router as status_router
from pocketquant.bff.market_data.handlers.sync.router import router as sync_router
from pocketquant.bff.market_data.handlers.tracked_symbols import router as tracked_symbols_router

router = APIRouter(prefix="/market-data", tags=["Market Data"])

router.include_router(sync_router)
router.include_router(integrity_router)
router.include_router(ohlcv_router)
router.include_router(status_router)
router.include_router(list_symbols_router)
router.include_router(tracked_symbols_router)
