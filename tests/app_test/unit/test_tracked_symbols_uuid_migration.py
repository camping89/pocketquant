"""Tests for migrate_tracked_symbols_uuid_ids — boot-time _id re-key to uuid7.

Legacy tracked_symbols docs used the composite symbol string as ``_id``.
The migration copy-deletes those docs with a fresh uuid7 ``_id`` (Mongo
forbids in-place ``_id`` updates), preserving all other fields. Docs whose
``_id`` already parses as a UUID are untouched — second run is a no-op.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide

from pocketquant.app.main_extensions import migrate_tracked_symbols_uuid_ids
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


def _legacy_doc(symbol: str) -> dict:
    """Pre-migration shape — composite symbol doubles as _id."""
    return {
        "_id": symbol,
        "symbol": symbol,
        "created_at": datetime(2026, 1, 15, tzinfo=UTC),
        "seeded_from": "auto-seed",
    }


@pytest.mark.asyncio
async def test_rekeys_legacy_docs_preserving_fields(container) -> None:
    db = await container.get(Database)
    coll = db.database["tracked_symbols"]

    await coll.insert_many(
        [_legacy_doc("BTCUSDT:BINANCE"), _legacy_doc("ETHUSDT:OKX")]
    )

    await migrate_tracked_symbols_uuid_ids(container)

    docs = await coll.find({}).to_list(length=10)
    assert len(docs) == 2
    by_symbol = {d["symbol"]: d for d in docs}
    for symbol in ("BTCUSDT:BINANCE", "ETHUSDT:OKX"):
        doc = by_symbol[symbol]
        assert UUID(doc["_id"]).version == 7
        assert doc["symbol"] == symbol
        # pymongo returns BSON dates as naive UTC by default
        assert doc["created_at"] == datetime(2026, 1, 15)  # noqa: DTZ001
        assert doc["seeded_from"] == "auto-seed"


@pytest.mark.asyncio
async def test_idempotent_second_run_keeps_ids(container) -> None:
    db = await container.get(Database)
    coll = db.database["tracked_symbols"]

    await coll.insert_one(_legacy_doc("BTCUSDT:BINANCE"))

    await migrate_tracked_symbols_uuid_ids(container)
    first = await coll.find_one({"symbol": "BTCUSDT:BINANCE"})

    await migrate_tracked_symbols_uuid_ids(container)
    second = await coll.find_one({"symbol": "BTCUSDT:BINANCE"})

    assert second["_id"] == first["_id"]
    assert await coll.count_documents({}) == 1


@pytest.mark.asyncio
async def test_already_uuid_docs_untouched(container) -> None:
    db = await container.get(Database)
    coll = db.database["tracked_symbols"]

    existing_id = generate_id_str()
    await coll.insert_one(
        {
            "_id": existing_id,
            "symbol": "SOLUSDT:BINANCE",
            "created_at": datetime(2026, 2, 1, tzinfo=UTC),
            "seeded_from": "admin",
        }
    )

    await migrate_tracked_symbols_uuid_ids(container)

    doc = await coll.find_one({"symbol": "SOLUSDT:BINANCE"})
    assert doc["_id"] == existing_id


@pytest.mark.asyncio
async def test_creates_unique_symbol_index(container) -> None:
    db = await container.get(Database)
    coll = db.database["tracked_symbols"]

    await coll.insert_one(_legacy_doc("BTCUSDT:BINANCE"))
    await migrate_tracked_symbols_uuid_ids(container)

    indexes = await coll.index_information()
    ix = indexes.get("ix_tracked_symbols_symbol")
    assert ix is not None
    assert ix.get("unique") is True


@pytest.mark.asyncio
async def test_replaces_same_name_non_unique_index_with_unique(container) -> None:
    db = await container.get(Database)
    coll = db.database["tracked_symbols"]

    # Old deploy shape: same index name but without the unique option —
    # create_index raises IndexKeySpecsConflict (code 86).
    await coll.create_index([("symbol", 1)], name="ix_tracked_symbols_symbol")

    await migrate_tracked_symbols_uuid_ids(container)

    indexes = await coll.index_information()
    assert indexes["ix_tracked_symbols_symbol"].get("unique") is True


@pytest.mark.asyncio
async def test_empty_collection_is_noop(container) -> None:
    db = await container.get(Database)
    coll = db.database["tracked_symbols"]

    await migrate_tracked_symbols_uuid_ids(container)

    assert await coll.count_documents({}) == 0
