"""OHLCV sub-feature router - aggregates OHLCV operation routes."""

from fastapi import APIRouter

from src.features.market_data.ohlcv.get_ohlcv.route import router as get_ohlcv_router

router = APIRouter()

# Include operation routers
router.include_router(get_ohlcv_router)
