"""Sync sub-feature router - aggregates sync operation routes."""

from fastapi import APIRouter

from src.features.market_data.sync.sync_bulk.route import router as sync_bulk_router
from src.features.market_data.sync.sync_one.route import router as sync_one_router

router = APIRouter()

# Include operation routers
router.include_router(sync_one_router)
router.include_router(sync_bulk_router)
