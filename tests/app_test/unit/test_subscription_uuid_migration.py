"""Tests for migrate_subscription_uuid_ids — boot-time subscriptions _id re-key + FK rewrite.

Legacy subscription docs carried a deterministic sha256 16-hex ``_id``; four
collections reference it: ``orders.subscription_id``, ``positions.subscription_id``,
``backtest_runs.subscription_id``, ``backtest_requests.sub_id``. The migration is
map-based so a crash mid-rewrite resumes instead of forking ids:

  1. ensure the dedup triple unique index FIRST (guarantee never lapses);
  2. persist ``{old_id, new_id}`` pairs into ``_id_migration_map`` (upsert by
     old_id — re-runs reuse the same new_id);
  3. rewrite the subscription doc + all 4 FK fields from the map (each step
     filters on the old value, so re-runs are no-ops);
  4. verify no old_id remains anywhere, then drop the map; on residue keep the
     map and continue boot (next boot retries).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide

from pocketquant.app.main_extensions import migrate_subscription_uuid_ids
from pocketquant.core.common.uuid import UUID, generate_id_str
from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.mongodb import Database

_FK_FIELDS = [
    ("orders", "subscription_id"),
    ("positions", "subscription_id"),
    ("backtest_runs", "subscription_id"),
    ("backtest_requests", "sub_id"),
]


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


def _legacy_sub_doc(sub_id: str, *, symbol: str = "BTCUSDT:BINANCE") -> dict:
    return {
        "_id": sub_id,
        "strategy_code": "hitnrun2",
        "symbol": symbol,
        "interval": "1h",
        "created_at": datetime(2026, 6, 1, tzinfo=UTC),
        "desired_state": "running",
        "actual_state": "running",
    }


async def _seed_fk_docs(db: Database, sub_id: str) -> None:
    """One referencing doc per FK collection, keyed off the legacy sub id."""
    await db.database["orders"].insert_one(
        {"_id": generate_id_str(), "subscription_id": sub_id, "symbol": "BTCUSDT:BINANCE"}
    )
    await db.database["positions"].insert_one(
        {"_id": generate_id_str(), "subscription_id": sub_id, "symbol": "BTCUSDT:BINANCE"}
    )
    await db.database["backtest_runs"].insert_one(
        {"_id": generate_id_str(), "subscription_id": sub_id, "status": "completed"}
    )
    await db.database["backtest_requests"].insert_one(
        {"_id": generate_id_str(), "sub_id": sub_id, "kind": "subscription", "status": "done"}
    )


async def _assert_no_fk_references(db: Database, old_id: str) -> None:
    for coll, field in _FK_FIELDS:
        count = await db.database[coll].count_documents({field: old_id})
        assert count == 0, f"{coll}.{field} still references legacy id {old_id}"


@pytest.mark.asyncio
async def test_rekeys_subs_and_rewrites_all_fk_fields(container) -> None:
    db = await container.get(Database)
    subs = db.database["subscriptions"]

    legacy_a = _legacy_sub_doc("eef73dffbd77a20b", symbol="BTCUSDT:BINANCE")
    legacy_b = _legacy_sub_doc("abc123def4567890", symbol="ETHUSDT:BINANCE")
    already_uuid = {**_legacy_sub_doc(generate_id_str(), symbol="SOLUSDT:BINANCE")}
    await subs.insert_many([legacy_a, legacy_b, already_uuid])
    await _seed_fk_docs(db, "eef73dffbd77a20b")
    await _seed_fk_docs(db, "abc123def4567890")

    await migrate_subscription_uuid_ids(container)

    assert await subs.count_documents({}) == 3

    for old_id, symbol in [
        ("eef73dffbd77a20b", "BTCUSDT:BINANCE"),
        ("abc123def4567890", "ETHUSDT:BINANCE"),
    ]:
        assert await subs.find_one({"_id": old_id}) is None
        rekeyed = await subs.find_one({"symbol": symbol})
        assert rekeyed is not None
        new_id = rekeyed["_id"]
        assert UUID(new_id).version == 7
        # Payload survives the re-key.
        assert rekeyed["strategy_code"] == "hitnrun2"
        assert rekeyed["desired_state"] == "running"
        # Every FK collection now points at the new id, none at the old.
        await _assert_no_fk_references(db, old_id)
        for coll, field in _FK_FIELDS:
            assert await db.database[coll].count_documents({field: new_id}) == 1

    # Pre-existing uuid sub untouched (same _id, no FK docs seeded for it).
    untouched = await subs.find_one({"symbol": "SOLUSDT:BINANCE"})
    assert untouched is not None
    assert untouched["_id"] == already_uuid["_id"]

    # Map collection self-cleans after successful verify.
    assert "_id_migration_map" not in await db.database.list_collection_names()


@pytest.mark.asyncio
async def test_idempotent_second_run_no_changes(container) -> None:
    db = await container.get(Database)
    subs = db.database["subscriptions"]
    await subs.insert_one(_legacy_sub_doc("eef73dffbd77a20b"))
    await _seed_fk_docs(db, "eef73dffbd77a20b")

    await migrate_subscription_uuid_ids(container)
    first = await subs.find_one({"symbol": "BTCUSDT:BINANCE"})

    await migrate_subscription_uuid_ids(container)
    second = await subs.find_one({"symbol": "BTCUSDT:BINANCE"})

    assert second["_id"] == first["_id"]
    assert await subs.count_documents({}) == 1
    order = await db.database["orders"].find_one({})
    assert order["subscription_id"] == first["_id"]


@pytest.mark.asyncio
async def test_crash_resume_existing_map_entry_reused(container) -> None:
    """Map persisted but rewrite incomplete (crash between steps): re-run uses
    the SAME new_id from the map and finishes the FK rewrite — ids never fork."""
    db = await container.get(Database)
    subs = db.database["subscriptions"]
    old_id = "eef73dffbd77a20b"
    pinned_new_id = generate_id_str()

    await subs.insert_one(_legacy_sub_doc(old_id))
    await _seed_fk_docs(db, old_id)
    # Simulate prior run that wrote the map then died before any rewrite.
    await db.database["_id_migration_map"].insert_one(
        {"_id": old_id, "new_id": pinned_new_id}
    )

    await migrate_subscription_uuid_ids(container)

    rekeyed = await subs.find_one({"symbol": "BTCUSDT:BINANCE"})
    assert rekeyed is not None
    assert rekeyed["_id"] == pinned_new_id  # map entry reused, not regenerated
    await _assert_no_fk_references(db, old_id)
    assert "_id_migration_map" not in await db.database.list_collection_names()


@pytest.mark.asyncio
async def test_crash_resume_half_rewritten_fks_completed(container) -> None:
    """Sub doc already re-keyed + some FKs rewritten, others not (crash mid-step 3):
    re-run completes only the remaining FK rewrites."""
    db = await container.get(Database)
    subs = db.database["subscriptions"]
    old_id = "eef73dffbd77a20b"
    new_id = generate_id_str()

    # Prior run finished the sub-doc copy-delete and the orders rewrite...
    await subs.insert_one({**_legacy_sub_doc(old_id), "_id": new_id})
    await db.database["orders"].insert_one(
        {"_id": generate_id_str(), "subscription_id": new_id, "symbol": "BTCUSDT:BINANCE"}
    )
    # ...but died before positions/backtest_runs/backtest_requests.
    await db.database["positions"].insert_one(
        {"_id": generate_id_str(), "subscription_id": old_id, "symbol": "BTCUSDT:BINANCE"}
    )
    await db.database["backtest_runs"].insert_one(
        {"_id": generate_id_str(), "subscription_id": old_id, "status": "completed"}
    )
    await db.database["backtest_requests"].insert_one(
        {"_id": generate_id_str(), "sub_id": old_id, "kind": "subscription", "status": "done"}
    )
    await db.database["_id_migration_map"].insert_one({"_id": old_id, "new_id": new_id})

    await migrate_subscription_uuid_ids(container)

    await _assert_no_fk_references(db, old_id)
    for coll, field in _FK_FIELDS:
        assert await db.database[coll].count_documents({field: new_id}) == 1
    assert "_id_migration_map" not in await db.database.list_collection_names()


@pytest.mark.asyncio
async def test_creates_dedup_triple_unique_index(container) -> None:
    db = await container.get(Database)

    await migrate_subscription_uuid_ids(container)

    info = await db.database["subscriptions"].index_information()
    idx = info["ix_subscriptions_dedup_triple"]
    assert idx.get("unique") is True
    assert idx["key"] == [("strategy_code", 1), ("symbol", 1), ("interval", 1)]


@pytest.mark.asyncio
async def test_no_legacy_docs_is_noop(container) -> None:
    db = await container.get(Database)
    subs = db.database["subscriptions"]
    doc = _legacy_sub_doc(generate_id_str())
    await subs.insert_one(doc)

    await migrate_subscription_uuid_ids(container)

    unchanged = await subs.find_one({})
    assert unchanged["_id"] == doc["_id"]
    assert "_id_migration_map" not in await db.database.list_collection_names()
