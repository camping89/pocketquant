"""HTTP endpoints for the Exness safeguards.

Exposes:
  - GET /admin/safeguards — the caps and the entry pause.
  - POST /admin/safeguards/pause and /resume — flip the entry pause and store it.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from pocketquant.core.infra.brokers.exness.exness_safeguards import Safeguards
from pocketquant.core.infra.persistence.repositories.safeguards_repository import (
    SafeguardsRepository,
)

router = APIRouter(prefix="/admin/safeguards", route_class=DishkaRoute)


@router.get("")
async def get_safeguards(safeguards: FromDishka[Safeguards]) -> dict[str, Any]:
    return asdict(safeguards)


@router.post("/pause")
async def pause_entries(
    safeguards: FromDishka[Safeguards], repo: FromDishka[SafeguardsRepository]
) -> dict[str, Any]:
    return await _set_entries_paused(safeguards, repo, paused=True)


@router.post("/resume")
async def resume_entries(
    safeguards: FromDishka[Safeguards], repo: FromDishka[SafeguardsRepository]
) -> dict[str, Any]:
    return await _set_entries_paused(safeguards, repo, paused=False)


async def _set_entries_paused(
    safeguards: Safeguards, repo: SafeguardsRepository, *, paused: bool
) -> dict[str, Any]:
    # The in-memory flag flips first, so a failed store write still leaves the pause in force.
    safeguards.set_entries_paused(paused)
    await repo.save_entries_paused(paused)
    return asdict(safeguards)
