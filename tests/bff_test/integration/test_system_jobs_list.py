"""GET /system/jobs reads raw APScheduler Mongo docs without a scheduler.

MongoDBJobStore persists ``next_run_time`` as a UTC float timestamp
(datetime_to_utc_timestamp), not a datetime — the route must convert it,
and tolerate None (paused job).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.mongodb import Database
from tests.bff_test.bff_app_factory import make_bff_test_app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def bff_client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = make_bff_test_app(settings)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def test_list_jobs_converts_float_next_run_and_tolerates_none(
    bff_client: AsyncClient, settings: Settings
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

        resp = await bff_client.get(f"{settings.api_prefix}/system/jobs")

        assert resp.status_code == 200, resp.text
        jobs = {j["id"]: j for j in resp.json()}
        assert jobs["market_data_sync"]["next_run"] == "2026-06-12T03:00:00+00:00"
        assert jobs["paused_job"]["next_run"] is None
    finally:
        await db.database["apscheduler_jobs"].delete_many({})
        await db.disconnect()
