"""Status sub-feature router — get_sync_status and get_symbol_sync_status only.

quote_service_status dropped: required a live QuoteAppService instance in bff.
"""

from fastapi import APIRouter

from pocketquant.bff.market_data.handlers.status.get_symbol_sync_status.route import (
    router as symbol_sync_status_router,
)
from pocketquant.bff.market_data.handlers.status.get_sync_status.route import (
    router as sync_status_router,
)

router = APIRouter()

router.include_router(sync_status_router)
router.include_router(symbol_sync_status_router)
