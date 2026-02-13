"""Status sub-feature router - aggregates status operation routes."""

from fastapi import APIRouter

from src.features.market_data.status.get_quote_service_status.route import (
    router as quote_service_status_router,
)
from src.features.market_data.status.get_symbol_sync_status.route import (
    router as symbol_sync_status_router,
)
from src.features.market_data.status.get_sync_status.route import (
    router as sync_status_router,
)

router = APIRouter()

# Include operation routers
router.include_router(sync_status_router)
router.include_router(symbol_sync_status_router)
router.include_router(quote_service_status_router)
