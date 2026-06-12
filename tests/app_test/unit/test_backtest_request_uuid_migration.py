"""Tests for migrate_backtest_request_ids — boot-time _id re-key to uuid7.

Legacy subscription-kind requests carry a deterministic ``bt:{sub_id}`` _id
(the old dedup mechanism). The migration first creates the partial unique
index on (sub_id, status=pending) — the new DB-level dedup guarantee — then
re-keys each ``bt:``-prefixed doc to a fresh uuid7 _id (Mongo forbids
in-place _id updates: delete + re-insert, fields preserved). Pending docs sit
inside the unique index, so delete-before-insert is mandatory; the full doc
is logged before the delete so a crash between the two ops is recoverable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide

from pocketquant.app.main_extensions import migrate_backtest_request_ids
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


def _legacy_doc(sub_id: str, *, status: str = "pending") -> dict:
    """Old subscription-kind request shape with the deterministic bt: _id."""
    return {
        "_id": f"bt:{sub_id}",
        "kind": "subscription",
        "status": status,
        "requested_at": datetime(2026, 6, 1, tzinfo=UTC),
        "sub_id": sub_id,
        "strategy_code": "hitnrun2",
        "config": None,
        "result": None,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "metadata": {},
    }


@pytest.mark.asyncio
async def test_rekeys_bt_prefixed_docs_preserving_fields(container) -> None:
    db = await container.get(Database)
    coll = db.database["backtest_requests"]

    legacy_pending = _legacy_doc("sub-aaa", status="pending")
    legacy_done = _legacy_doc("sub-bbb", status="done")
    uuid_id = generate_id_str()
    await coll.insert_many(
        [
            legacy_pending,
            legacy_done,
            {**_legacy_doc("sub-ccc"), "_id": uuid_id},
        ]
    )

    await migrate_backtest_request_ids(container)

    docs = await coll.find({}).to_list(length=10)
    assert len(docs) == 3
    by_sub = {d["sub_id"]: d for d in docs}
    for sub_id, source in (("sub-aaa", legacy_pending), ("sub-bbb", legacy_done)):
        doc = by_sub[sub_id]
        assert UUID(doc["_id"]).version == 7
        # All payload fields survive the re-key.
        assert doc["kind"] == source["kind"]
        assert doc["status"] == source["status"]
        assert doc["strategy_code"] == source["strategy_code"]
        # pymongo returns BSON dates as naive UTC by default
        assert doc["requested_at"] == source["requested_at"].replace(tzinfo=None)
    # Already-uuid doc untouched.
    assert by_sub["sub-ccc"]["_id"] == uuid_id
    # No bt:-prefixed doc remains.
    assert await coll.count_documents({"_id": {"$regex": "^bt:"}}) == 0


@pytest.mark.asyncio
async def test_idempotent_second_run_keeps_count_and_ids(container) -> None:
    db = await container.get(Database)
    coll = db.database["backtest_requests"]

    await coll.insert_one(_legacy_doc("sub-aaa"))

    await migrate_backtest_request_ids(container)
    first = await coll.find_one({"sub_id": "sub-aaa"})

    await migrate_backtest_request_ids(container)
    second = await coll.find_one({"sub_id": "sub-aaa"})

    assert second["_id"] == first["_id"]
    assert await coll.count_documents({}) == 1


@pytest.mark.asyncio
async def test_creates_partial_unique_pending_index(container) -> None:
    db = await container.get(Database)
    coll = db.database["backtest_requests"]

    await migrate_backtest_request_ids(container)

    info = await coll.index_information()
    idx = info["ix_backtest_requests_pending_sub"]
    assert idx.get("unique") is True
    assert idx["partialFilterExpression"] == {
        "status": "pending",
        "sub_id": {"$type": "string"},
    }


@pytest.mark.asyncio
async def test_null_sub_id_docs_not_constrained_by_index(container) -> None:
    """Single-kind requests (sub_id=None) must never collide in the partial
    index — two pending single runs are legitimate concurrent work."""
    db = await container.get(Database)
    coll = db.database["backtest_requests"]

    await migrate_backtest_request_ids(container)

    single = {**_legacy_doc("ignored"), "kind": "single", "sub_id": None}
    await coll.insert_one({**single, "_id": generate_id_str()})
    # Second pending doc with null sub_id — must NOT raise DuplicateKeyError.
    await coll.insert_one({**single, "_id": generate_id_str()})
    assert await coll.count_documents({"sub_id": None, "status": "pending"}) == 2
