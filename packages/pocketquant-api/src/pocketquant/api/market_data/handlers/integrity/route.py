"""Integrity check and repair endpoints for bar data."""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter
from pocketquant.api.common.symbol_validation import validate_composite_symbol
from pocketquant.api.market_data.app_services.integrity_jobs import (
    check_integrity,
    repair_integrity,
)
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.infrastructure.persistence.repositories.bar_repository import BarRepository
from pydantic import BaseModel, Field


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
    mediator: FromDishka[Mediator],
) -> dict:
    symbol = validate_composite_symbol(body.symbol)
    return await repair_integrity(symbol, body.interval, bar_repo, mediator, body.days_back)
