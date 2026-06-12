"""Tests for migrate_job_history_uuid_ids — boot-time _id re-key to uuid7.

Legacy job_history docs (pre-uuid write path) carry a Mongo ObjectId ``_id``.
The migration copies each one with a fresh uuid7 ``_id`` (Mongo forbids
in-place ``_id`` updates) and then deletes the original. The collection is an
append-only log with no FK consumers, so insert-before-delete preserves the
history even if the process dies between the two ops; the ``_migrated_from``
marker on the copy makes crash-resume skip the re-insert instead of
duplicating the record.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio

# ObjectId is repo-banned for production ids; this module is the one place
# that must FABRICATE the legacy shape the migration erases.
from bson import ObjectId  # noqa: TID251
from dishka import Provider, Scope, make_async_container, provide

from pocketquant.app.main_extensions import migrate_job_history_uuid_ids
from pocketquant.core.common.uuid import UUID, generate_id_str
from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.mongodb import Database


class _TestProvider(Provider):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        return self._settings

    @provide(scope=Scope.APP)
    async def get_database(self, settings: Settings) -> AsyncIterator[Database]:
        db = Database()
        await db.connect(settings)
        yield db
        await db.disconnect()


@pytest_asyncio.fixture(autouse=True)
async def _reset_db(settings: Settings):
    db = Database()
    await db.connect(settings)
    try:
        await db.database.client.drop_database(settings.mongodb_database)
    finally:
        await db.disconnect()
    yield


@pytest_asyncio.fixture
async def container(settings: Settings):
    c = make_async_container(_TestProvider(settings))
    yield c
    await c.close()


def _legacy_doc(job_id: str, *, started_at: datetime) -> dict:
    """Pre-uuid wrapper-path shape — Mongo assigned the ObjectId _id."""
    return {
        "_id": ObjectId(),
        "job_id": job_id,
        "started_at": started_at,
        "finished_at": started_at,
        "duration_ms": 1234,
        "status": "completed",
        "error": None,
        "details": [],
        "total_inserted": 7,
        "total_fetched": 60,
    }


@pytest.mark.asyncio
async def test_rekeys_legacy_docs_preserving_fields(container) -> None:
    db = await container.get(Database)
    coll = db.database["job_history"]

    legacy_a = _legacy_doc("sync_5m", started_at=datetime(2026, 5, 1, tzinfo=UTC))
    legacy_b = _legacy_doc("sync_15m", started_at=datetime(2026, 5, 2, tzinfo=UTC))
    uuid_id = generate_id_str()
    await coll.insert_many(
        [
            legacy_a,
            legacy_b,
            {**_legacy_doc("sync_1h", started_at=datetime(2026, 5, 3, tzinfo=UTC)), "_id": uuid_id},
        ]
    )

    await migrate_job_history_uuid_ids(container)

    docs = await coll.find({}).to_list(length=10)
    assert len(docs) == 3
    by_job = {d["job_id"]: d for d in docs}
    for job_id, source in (("sync_5m", legacy_a), ("sync_15m", legacy_b)):
        doc = by_job[job_id]
        assert UUID(doc["_id"]).version == 7
        # All payload fields survive the re-key.
        # pymongo returns BSON dates as naive UTC by default
        assert doc["started_at"] == source["started_at"].replace(tzinfo=None)
        assert doc["duration_ms"] == source["duration_ms"]
        assert doc["status"] == source["status"]
        assert doc["total_inserted"] == source["total_inserted"]
        assert doc["total_fetched"] == source["total_fetched"]
    # Already-uuid doc untouched.
    assert by_job["sync_1h"]["_id"] == uuid_id
    # No ObjectId-keyed doc remains.
    assert await coll.count_documents({"_id": {"$type": "objectId"}}) == 0


@pytest.mark.asyncio
async def test_idempotent_second_run_keeps_count_and_ids(container) -> None:
    db = await container.get(Database)
    coll = db.database["job_history"]

    await coll.insert_one(_legacy_doc("sync_5m", started_at=datetime(2026, 5, 1, tzinfo=UTC)))

    await migrate_job_history_uuid_ids(container)
    first = await coll.find_one({"job_id": "sync_5m"})

    await migrate_job_history_uuid_ids(container)
    second = await coll.find_one({"job_id": "sync_5m"})

    assert second["_id"] == first["_id"]
    assert await coll.count_documents({}) == 1


@pytest.mark.asyncio
async def test_crash_resume_does_not_duplicate(container) -> None:
    """Simulate a crash after the copy insert but before the legacy delete:
    both the ObjectId doc and its uuid copy (tagged ``_migrated_from``) are on
    disk. Re-running must delete the legacy doc WITHOUT inserting a second copy.
    """
    db = await container.get(Database)
    coll = db.database["job_history"]

    legacy = _legacy_doc("sync_5m", started_at=datetime(2026, 5, 1, tzinfo=UTC))
    copy_id = generate_id_str()
    await coll.insert_many(
        [
            legacy,
            {
                **{k: v for k, v in legacy.items() if k != "_id"},
                "_id": copy_id,
                "_migrated_from": str(legacy["_id"]),
            },
        ]
    )

    await migrate_job_history_uuid_ids(container)

    docs = await coll.find({"job_id": "sync_5m"}).to_list(length=10)
    assert len(docs) == 1
    assert docs[0]["_id"] == copy_id
    assert await coll.count_documents({"_id": {"$type": "objectId"}}) == 0


@pytest.mark.asyncio
async def test_rekeys_legacy_skip_doc_under_unique_index(container) -> None:
    """Legacy listener-path docs (ObjectId _id + date scheduled_run_time) sit
    inside the unique partial index idx_skip_idempotency. Inserting the uuid
    copy collides with the legacy doc on (job_id, scheduled_run_time) — the
    migration must free the slot (delete legacy first) and still re-key.
    """
    from pocketquant.core.infra.persistence.repositories.job_history_repository import (
        JobHistoryRepository,
    )

    db = await container.get(Database)
    coll = db.database["job_history"]
    await JobHistoryRepository(db).ensure_indexes()

    sched = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
    await coll.insert_one(
        {
            "_id": ObjectId(),
            "job_id": "sync_5m",
            "scheduled_run_time": sched,
            "started_at": sched,
            "finished_at": sched,
            "duration_ms": 0,
            "status": "missed",
            "error": None,
            "details": [],
            "total_inserted": 0,
            "total_fetched": 0,
        }
    )

    await migrate_job_history_uuid_ids(container)

    docs = await coll.find({"job_id": "sync_5m"}).to_list(length=10)
    assert len(docs) == 1
    assert UUID(docs[0]["_id"]).version == 7
    assert docs[0]["status"] == "missed"
    assert docs[0]["scheduled_run_time"] == sched.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_empty_collection_is_noop(container) -> None:
    db = await container.get(Database)
    coll = db.database["job_history"]

    await migrate_job_history_uuid_ids(container)

    assert await coll.count_documents({}) == 0
