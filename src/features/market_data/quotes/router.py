"""Quote API - collects sub-routers from quote operation folders."""

from fastapi import APIRouter

from src.features.market_data.quotes.get_all.route import router as get_all_router
from src.features.market_data.quotes.get_current_bar.route import (
    router as current_bar_router,
)
from src.features.market_data.quotes.get_latest.route import (
    router as get_latest_router,
)
from src.features.market_data.quotes.start_feed.route import (
    router as start_feed_router,
)
from src.features.market_data.quotes.stop_feed.route import (
    router as stop_feed_router,
)
from src.features.market_data.quotes.subscribe.route import router as subscribe_router
from src.features.market_data.quotes.unsubscribe.route import router as unsubscribe_router

router = APIRouter(prefix="/quotes", tags=["Real-time Quotes"])

# Include all operation routers
router.include_router(start_feed_router)
router.include_router(stop_feed_router)
router.include_router(subscribe_router)
router.include_router(unsubscribe_router)
router.include_router(get_latest_router)
router.include_router(get_all_router)
router.include_router(current_bar_router)
