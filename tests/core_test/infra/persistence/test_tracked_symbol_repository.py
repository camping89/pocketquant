"""Integration tests for TrackedSymbolRepository — upsert idempotency, uuid7 _id, dedup."""

from __future__ import annotations

import pytest
from pymongo.errors import DuplicateKeyError

from pocketquant.core.common.uuid import UUID
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

pytestmark = pytest.mark.integration


# Fixtures


@pytest.fixture
async def db(settings):
    database = Database()
    await database.connect(settings)
    await database.get_collection(TrackedSymbolRepository._collection_name).drop()
    yield database
    await database.disconnect()


@pytest.fixture
async def repo(db):
    r = TrackedSymbolRepository(db)
    await r.ensure_indexes()
    return r


# Tests


@pytest.mark.asyncio
async def test_upsert_twice_same_symbol_yields_one_doc_with_stable_id(repo, db):
    coll = db.get_collection(TrackedSymbolRepository._collection_name)

    await repo.upsert(TrackedSymbol(symbol="BTCUSDT:BINANCE", seeded_from="admin"))
    first = await coll.find_one({"symbol": "BTCUSDT:BINANCE"})

    await repo.upsert(TrackedSymbol(symbol="BTCUSDT:BINANCE", seeded_from="auto-seed"))
    docs = await coll.find({"symbol": "BTCUSDT:BINANCE"}).to_list(length=10)

    assert len(docs) == 1
    # $setOnInsert keeps the original _id — second upsert must not re-key
    assert docs[0]["_id"] == first["_id"]
    assert docs[0]["seeded_from"] == "auto-seed"


@pytest.mark.asyncio
async def test_upsert_writes_uuid7_id(repo, db):
    coll = db.get_collection(TrackedSymbolRepository._collection_name)

    await repo.upsert(TrackedSymbol(symbol="ETHUSDT:BINANCE"))
    doc = await coll.find_one({"symbol": "ETHUSDT:BINANCE"})

    parsed = UUID(doc["_id"])
    assert parsed.version == 7


@pytest.mark.asyncio
async def test_two_symbols_yield_two_docs(repo, db):
    coll = db.get_collection(TrackedSymbolRepository._collection_name)

    await repo.upsert(TrackedSymbol(symbol="BTCUSDT:BINANCE"))
    await repo.upsert(TrackedSymbol(symbol="ETHUSDT:OKX"))

    assert await coll.count_documents({}) == 2


@pytest.mark.asyncio
async def test_direct_duplicate_symbol_insert_raises(repo, db):
    coll = db.get_collection(TrackedSymbolRepository._collection_name)

    await repo.upsert(TrackedSymbol(symbol="SOLUSDT:BINANCE"))
    dup = TrackedSymbol(symbol="SOLUSDT:BINANCE")

    with pytest.raises(DuplicateKeyError):
        await coll.insert_one(dup.to_mongo())


@pytest.mark.asyncio
async def test_round_trip_preserves_uuid_id(repo):
    ts = TrackedSymbol(symbol="XRPUSDT:OKX", seeded_from="admin")
    await repo.upsert(ts)

    fetched = await repo.list_all()
    assert len(fetched) == 1
    assert isinstance(fetched[0].id, UUID)
    assert fetched[0].id == ts.id
    assert fetched[0].symbol == "XRPUSDT:OKX"
    assert fetched[0].seeded_from == "admin"


@pytest.mark.asyncio
async def test_exists_update_delete_by_symbol(repo):
    await repo.upsert(TrackedSymbol(symbol="BNBUSDT:BINANCE"))

    assert await repo.exists("BNBUSDT:BINANCE") is True
    assert await repo.exists("NOPE:BINANCE") is False

    assert await repo.update("BNBUSDT:BINANCE", {}) is True
    assert await repo.update("NOPE:BINANCE", {}) is False

    assert await repo.delete("BNBUSDT:BINANCE") is True
    assert await repo.delete("BNBUSDT:BINANCE") is False
    assert await repo.exists("BNBUSDT:BINANCE") is False
