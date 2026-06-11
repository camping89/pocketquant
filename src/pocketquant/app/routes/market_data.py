"""Market data router — aggregates all market data feature routers under /market-data."""

from fastapi import APIRouter

from pocketquant.app.routes.integrity import router as integrity_router
from pocketquant.app.routes.list_symbols import router as list_symbols_router
from pocketquant.app.routes.market_data_ohlcv import router as ohlcv_router
from pocketquant.app.routes.market_data_status import router as status_router
from pocketquant.app.routes.market_data_sync import router as sync_router
from pocketquant.app.routes.tracked_symbols import router as tracked_symbols_router

router = APIRouter(prefix="/market-data", tags=["Market Data"])

router.include_router(sync_router)
router.include_router(integrity_router)
router.include_router(ohlcv_router)
router.include_router(status_router)
router.include_router(list_symbols_router)
router.include_router(tracked_symbols_router)
