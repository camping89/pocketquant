from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Request

from pocketquant.core.common.logging import get_logger
from pocketquant.core.infra.brokers.exness.exness_safeguards import Safeguards
from pocketquant.core.infra.persistence.repositories.safeguards_repository import (
    SafeguardsRepository,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/safeguards", route_class=DishkaRoute)

_READ_CACHE_S = 1.0


@router.get("")
async def get_safeguards(
    request: Request, safeguards: FromDishka[Safeguards], repo: FromDishka[SafeguardsRepository]
) -> dict[str, Any]:
    # The read is public: at most one store read per second per process, so a flood
    # cannot load the store the open path reads.
    cached = getattr(request.app.state, "entries_paused_read", None)
    if cached is None or time.monotonic() - cached[0] > _READ_CACHE_S:
        cached = (time.monotonic(), await repo.load_entries_paused())
        request.app.state.entries_paused_read = cached
    return asdict(safeguards) | {"entries_paused": cached[1]}


@router.post("/pause")
async def pause_entries(
    request: Request, safeguards: FromDishka[Safeguards], repo: FromDishka[SafeguardsRepository]
) -> dict[str, Any]:
    return await _set_entries_paused(request, safeguards, repo, paused=True)


@router.post("/resume")
async def resume_entries(
    request: Request, safeguards: FromDishka[Safeguards], repo: FromDishka[SafeguardsRepository]
) -> dict[str, Any]:
    return await _set_entries_paused(request, safeguards, repo, paused=False)


async def _set_entries_paused(
    request: Request, safeguards: Safeguards, repo: SafeguardsRepository, *, paused: bool
) -> dict[str, Any]:
    try:
        await repo.save_entries_paused(paused)
    except Exception:
        logger.warning("exness.safeguards.pause_store_failed", paused=paused)
        raise HTTPException(status_code=503, detail="pause not stored") from None
    request.app.state.entries_paused_read = (time.monotonic(), paused)
    logger.warning(
        "exness.safeguards.entries_paused" if paused else "exness.safeguards.entries_resumed"
    )
    return asdict(safeguards) | {"entries_paused": paused}
