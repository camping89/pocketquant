"""tracked_symbols feature — aggregates all CRUD + backfill routes under /tracked-symbols."""

from fastapi import APIRouter
from pocketquant.bff.market_data.handlers.tracked_symbols.add.route import router as add_router
from pocketquant.bff.market_data.handlers.tracked_symbols.backfill.route import (
    router as backfill_router,
)
from pocketquant.bff.market_data.handlers.tracked_symbols.list_all.route import (
    router as list_router,
)
from pocketquant.bff.market_data.handlers.tracked_symbols.remove.route import (
    router as remove_router,
)
from pocketquant.bff.market_data.handlers.tracked_symbols.update.route import (
    router as update_router,
)

router = APIRouter(tags=["Tracked Symbols"])
router.include_router(list_router)
router.include_router(add_router)
router.include_router(update_router)
router.include_router(remove_router)
router.include_router(backfill_router)
