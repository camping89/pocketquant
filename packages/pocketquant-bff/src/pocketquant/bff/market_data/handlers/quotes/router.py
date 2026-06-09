"""Quote API — get_latest, get_current_bar, stream_quote only.

Live-runtime endpoints (get_all, get_status/subscribe-count, subscribe, unsubscribe)
are dropped: FE never calls them and they required WS runtime in bff.
"""

from fastapi import APIRouter
from pocketquant.bff.market_data.handlers.quotes.get_current_bar.route import (
    router as current_bar_router,
)
from pocketquant.bff.market_data.handlers.quotes.get_latest.route import (
    router as get_latest_router,
)
from pocketquant.bff.market_data.handlers.quotes.stream_quote.route import (
    router as stream_quote_router,
)

router = APIRouter(prefix="/quotes", tags=["Real-time Quotes"])

router.include_router(get_latest_router)
router.include_router(current_bar_router)
router.include_router(stream_quote_router)
