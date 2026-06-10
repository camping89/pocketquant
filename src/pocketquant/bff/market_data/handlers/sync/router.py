"""Sync sub-feature router - aggregates sync operation routes."""

from fastapi import APIRouter

from pocketquant.bff.market_data.handlers.sync.sync_bulk.router import router as sync_bulk_router
from pocketquant.bff.market_data.handlers.sync.sync_one.route import router as sync_one_router

router = APIRouter()

router.include_router(sync_one_router)
router.include_router(sync_bulk_router)
