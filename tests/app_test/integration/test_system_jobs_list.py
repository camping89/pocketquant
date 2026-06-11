"""GET /system/jobs reads raw APScheduler Mongo docs without a scheduler.

MongoDBJobStore persists ``next_run_time`` as a UTC float timestamp
(datetime_to_utc_timestamp), not a datetime — the route must convert it,
and tolerate None (paused job).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.mongodb import Database

pytestmark = pytest.mark.asyncio


async def test_list_jobs_converts_float_next_run_and_tolerates_none(
    app_client: AsyncClient, settings: Settings
) -> None:
    db = Database()
    await db.connect(settings)
    try:
        coll = db.database["apscheduler_jobs"]
        await coll.delete_many({})
        ts = datetime(2026, 6, 12, 3, 0, tzinfo=UTC).timestamp()
        await coll.insert_many(
            [
                {"_id": "market_data_sync", "next_run_time": ts, "job_state": b""},
                {"_id": "paused_job", "next_run_time": None, "job_state": b""},
            ]
        )

        resp = await app_client.get(f"{settings.api_prefix}/system/jobs")

        assert resp.status_code == 200, resp.text
        jobs = {j["id"]: j for j in resp.json()}
        assert jobs["market_data_sync"]["next_run"] == "2026-06-12T03:00:00+00:00"
        assert jobs["paused_job"]["next_run"] is None
    finally:
        await db.database["apscheduler_jobs"].delete_many({})
        await db.disconnect()
