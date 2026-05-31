"""HTTP endpoints for job history observability.

Exposes:
  - GET /system/jobs/{job_id}/runs — paginated history (newest first).
  - GET /system/jobs/{job_id}/stats — aggregated counts + p50/p95.

Stats are cached in Redis (30s) to avoid hammering Mongo aggregations
on every UI refresh.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query
from pocketquant.infrastructure.persistence import Cache
from pocketquant.infrastructure.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)

router = APIRouter(prefix="/system/jobs", route_class=DishkaRoute)

_STATS_CACHE_TTL = 30
_WINDOW_DAYS = {"24h": 1, "7d": 7, "30d": 30}


@router.get("/{job_id}/runs")
async def list_job_runs(
    job_id: str,
    history_repo: FromDishka[JobHistoryRepository],
    since: datetime | None = None,
    until: datetime | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    return await history_repo.find_runs(
        job_id,
        since=since,
        until=until,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}/stats")
async def get_job_stats(
    job_id: str,
    history_repo: FromDishka[JobHistoryRepository],
    cache: FromDishka[Cache],
    window: Literal["24h", "7d", "30d"] = "24h",
) -> dict[str, Any]:
    cache_key = f"job_stats:{job_id}:{window}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached
    since = datetime.now(UTC) - timedelta(days=_WINDOW_DAYS[window])
    data = await history_repo.aggregate_stats(job_id, since)
    payload = {"window": window, **data}
    await cache.set(cache_key, payload, ttl=_STATS_CACHE_TTL)
    return payload
