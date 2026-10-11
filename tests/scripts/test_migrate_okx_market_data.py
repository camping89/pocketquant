"""migrate_okx_market_data: inventory counts collisions, apply drops twins and renames the rest."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from uuid import uuid4

import pymongo
import pytest
from pymongo.database import Database
from testcontainers.mongodb import MongoDbContainer

from scripts.migrate_okx_market_data import apply, inventory, main

TWIN_DT = datetime(2026, 10, 5, 12, 0)
OKX_ONLY_DT = datetime(2026, 10, 5, 12, 1)


def _bar(symbol: str, dt: datetime) -> dict:
    return {"symbol": symbol, "interval": "1m", "datetime": dt, "close": 1.0}


@pytest.fixture
def db(mongo_container: MongoDbContainer) -> Iterator[Database]:
    client: pymongo.MongoClient = pymongo.MongoClient(mongo_container.get_connection_url())
    name = f"okx_migration_{uuid4().hex[:8]}"
    database = client[name]
    database.bars.create_index([("symbol", 1), ("interval", 1), ("datetime", 1)], unique=True)
    database.tracked_symbols.create_index("symbol", unique=True)
    database.bars.insert_many(
        [
            _bar("X:OKX", TWIN_DT),
            _bar("X:BINANCE", TWIN_DT),
            _bar("X:OKX", OKX_ONLY_DT),
        ]
    )
    database.tracked_symbols.insert_one({"symbol": "X:OKX"})
    try:
        yield database
    finally:
        client.drop_database(name)
        client.close()


def test_inventory_counts_okx_docs_and_collisions(db: Database) -> None:
    report = inventory(db)
    assert report["collections"]["bars"] == {"okx_docs": 2, "binance_docs": 1, "collisions": 1}
    assert report["collections"]["tracked_symbols"]["okx_docs"] == 1
    assert report["total_okx_docs"] == 3


def test_apply_requires_approval() -> None:
    assert main(["--apply"]) == 2


def test_apply_drops_twins_and_renames_the_rest(db: Database) -> None:
    result = apply(db)

    assert result["bars"] == {"renamed": 1, "dropped": 1}
    assert db.bars.count_documents({"symbol": {"$regex": ":OKX$"}}) == 0
    assert db.bars.count_documents({"symbol": "X:BINANCE"}) == 2
    assert db.tracked_symbols.find_one({}, {"_id": 0}) == {"symbol": "X:BINANCE"}
    assert inventory(db)["total_okx_docs"] == 0
