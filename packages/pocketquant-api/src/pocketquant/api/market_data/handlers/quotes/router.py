"""Quote API - collects sub-routers from quote operation folders.

BREAKING (P2): start_feed and stop_feed endpoints removed.
WS feed is now auto-started at app lifespan. Use GET /status for observability.
"""

from fastapi import APIRouter
from pocketquant.api.market_data.handlers.quotes.get_all.route import router as get_all_router
from pocketquant.api.market_data.handlers.quotes.get_current_bar.route import (
    router as current_bar_router,
)
from pocketquant.api.market_data.handlers.quotes.get_latest.route import (
    router as get_latest_router,
)
from pocketquant.api.market_data.handlers.quotes.get_status.route import (
    router as get_status_router,
)
from pocketquant.api.market_data.handlers.quotes.stream_quote.route import (
    router as stream_quote_router,
)
from pocketquant.api.market_data.handlers.quotes.subscribe.route import router as subscribe_router
from pocketquant.api.market_data.handlers.quotes.unsubscribe.route import (
    router as unsubscribe_router,
)

router = APIRouter(prefix="/quotes", tags=["Real-time Quotes"])

router.include_router(get_status_router)
router.include_router(subscribe_router)
router.include_router(unsubscribe_router)
router.include_router(get_latest_router)
router.include_router(get_all_router)
router.include_router(current_bar_router)
router.include_router(stream_quote_router)
