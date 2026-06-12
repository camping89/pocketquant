"""Tests for migrate_backtest_run_cache_ids — boot-time cache-doc _id re-key.

Legacy per-subscription cache docs in ``backtest_runs`` carried
``_id == subscription_id`` (16-hex). The slot guarantee (one cache doc per
subscription) now lives in the unique sparse index on ``subscription_id``,
so the index is ensured FIRST, then each legacy doc is re-keyed to a fresh
uuid7 ``_id`` (Mongo forbids in-place _id updates: delete + re-insert).
The legacy doc occupies the unique-index slot, so delete-before-insert is
mandatory; a crash between the two ops costs one cache entry that the next
backtest run repopulates. Single-run docs (no ``subscription_id`` field)
are never touched.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide

from pocketquant.app.main_extensions import migrate_backtest_run_cache_ids
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


def _legacy_cache_doc(sub_id: str, *, status: str = "completed") -> dict:
    """Old per-subscription cache shape: _id equals the 16-hex sub id."""
    return {
        "_id": sub_id,
        "subscription_id": sub_id,
        "strategy_code": "hitnrun2",
        "status": status,
        "last_run_at": datetime(2026, 6, 1, tzinfo=UTC),
        "metrics": {"total_trades": 3},
        "error_msg": None,
    }


def _single_run_doc() -> dict:
    """Single-run doc — uuid7 _id, no subscription_id field."""
    return {
        "_id": generate_id_str(),
        "strategy_code": "hitnrun2",
        "status": "completed",
        "started_at": datetime(2026, 6, 1, tzinfo=UTC),
    }


@pytest.mark.asyncio
async def test_rekeys_cache_docs_preserving_fields_and_skips_single_runs(container) -> None:
    db = await container.get(Database)
    coll = db.database["backtest_runs"]

    legacy = _legacy_cache_doc("eef73dffbd77a20b")
    single = _single_run_doc()
    await coll.insert_many([legacy, single])

    await migrate_backtest_run_cache_ids(container)

    docs = await coll.find({}).to_list(length=10)
    assert len(docs) == 2

    cache = await coll.find_one({"subscription_id": "eef73dffbd77a20b"})
    assert cache is not None
    assert UUID(cache["_id"]).version == 7
    assert cache["_id"] != cache["subscription_id"]
    # Payload fields survive the re-key (BSON dates come back naive UTC).
    assert cache["strategy_code"] == legacy["strategy_code"]
    assert cache["status"] == legacy["status"]
    assert cache["metrics"] == legacy["metrics"]
    assert cache["last_run_at"] == legacy["last_run_at"].replace(tzinfo=None)

    untouched = await coll.find_one({"_id": single["_id"]})
    assert untouched is not None
    assert "subscription_id" not in untouched


@pytest.mark.asyncio
async def test_idempotent_second_run_keeps_count_and_ids(container) -> None:
    db = await container.get(Database)
    coll = db.database["backtest_runs"]
    await coll.insert_one(_legacy_cache_doc("eef73dffbd77a20b"))

    await migrate_backtest_run_cache_ids(container)
    first = await coll.find_one({"subscription_id": "eef73dffbd77a20b"})

    await migrate_backtest_run_cache_ids(container)
    second = await coll.find_one({"subscription_id": "eef73dffbd77a20b"})

    assert second["_id"] == first["_id"]
    assert await coll.count_documents({}) == 1


@pytest.mark.asyncio
async def test_creates_unique_sparse_subscription_index(container) -> None:
    db = await container.get(Database)
    coll = db.database["backtest_runs"]

    await migrate_backtest_run_cache_ids(container)

    info = await coll.index_information()
    idx = info["ix_backtests_subscription_id_unique"]
    assert idx.get("unique") is True
    assert idx.get("sparse") is True


@pytest.mark.asyncio
async def test_status_only_cache_doc_rekeyed(container) -> None:
    """Lightweight 'running'/'failed' docs from upsert_status share the legacy shape."""
    db = await container.get(Database)
    coll = db.database["backtest_runs"]
    status_only = {
        "_id": "abc123def4567890",
        "subscription_id": "abc123def4567890",
        "strategy_code": "hitnrun2",
        "status": "failed",
        "last_run_at": datetime(2026, 6, 1, tzinfo=UTC),
        "error_msg": "boom",
    }
    await coll.insert_one(status_only)

    await migrate_backtest_run_cache_ids(container)

    doc = await coll.find_one({"subscription_id": "abc123def4567890"})
    assert doc is not None
    assert UUID(doc["_id"]).version == 7
    assert doc["status"] == "failed"
    assert doc["error_msg"] == "boom"
