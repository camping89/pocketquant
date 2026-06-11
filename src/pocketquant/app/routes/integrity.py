"""Integrity check and repair endpoints for bar data."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pydantic import BaseModel, Field

from pocketquant.app.common.symbol_validation import validate_composite_symbol
from pocketquant.core.domain.bar.entities import SOURCE_REST_REPAIR
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.market_data.app_services.integrity_jobs import (
    check_integrity,
    repair_integrity,
)
from pocketquant.engine.market_data.sync_service import SyncService


class IntegrityRequest(BaseModel):
    """Request body for integrity check/repair. ``symbol`` is composite ``{code}:{exchange}``."""

    symbol: str
    interval: Interval
    days_back: int = Field(default=7, ge=1, le=90)


router = APIRouter(route_class=DishkaRoute)


@router.post("/integrity/check")
async def integrity_check(
    body: IntegrityRequest,
    bar_repo: FromDishka[BarRepository],
) -> dict:
    symbol = validate_composite_symbol(body.symbol)
    return await check_integrity(symbol, body.interval, bar_repo, body.days_back)


@router.post("/integrity/repair")
async def integrity_repair(
    body: IntegrityRequest,
    bar_repo: FromDishka[BarRepository],
    sync_service: FromDishka[SyncService],
) -> dict:
    symbol = validate_composite_symbol(body.symbol)
    # source is keyword-only; days_back must be passed by name too (it follows the
    # `*` marker). Repaired bars are tagged with the REST-repair provenance.
    return await repair_integrity(
        symbol,
        body.interval,
        bar_repo,
        sync_service,
        source=SOURCE_REST_REPAIR,
        days_back=body.days_back,
    )
