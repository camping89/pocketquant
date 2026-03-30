"""OHLCV sub-feature router - aggregates OHLCV operation routes."""

from fastapi import APIRouter
from pocketquant.api.market_data.handlers.ohlcv.get_ohlcv.route import router as get_ohlcv_router
from pocketquant.api.market_data.handlers.ohlcv.stream_bars.route import router as stream_bars_router

router = APIRouter()

router.include_router(get_ohlcv_router)
router.include_router(stream_bars_router)
