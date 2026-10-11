"""Inventory or migrate ``:OKX`` market-data symbols to ``:BINANCE``.

OKX has no data policy, so a tracked ``X:OKX`` symbol must become ``X:BINANCE``. Where the
``:BINANCE`` twin of a document already exists under a collection's unique key, the ``:OKX``
document is dropped instead of renamed. Only top-level ``symbol`` fields are touched; nested
fields (``job_history.details[].symbol``) and Redis cache keys stay as historical records.

Reads ``MONGODB_URL`` and ``MONGODB_DATABASE`` from the environment. Runs from a file or
piped through stdin, e.g. ``docker exec -i pocketquant-app python - --inventory``.

    python scripts/migrate_okx_market_data.py --inventory
    python scripts/migrate_okx_market_data.py --apply --approved
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import pymongo
from pymongo.database import Database

UNIQUE_KEYS: dict[str, tuple[str, ...]] = {
    "bars": ("interval", "datetime"),
    "sync_status": ("interval",),
    "symbols": (),
    "tracked_symbols": (),
    "subscriptions": ("strategy_code", "interval"),
}

_OKX = {"symbol": {"$regex": ":OKX$"}}
_BINANCE = {"symbol": {"$regex": ":BINANCE$"}}
_SKIPPED = {"apscheduler_jobs"}


def _target(symbol: str) -> str:
    return symbol.removesuffix(":OKX") + ":BINANCE"


def _collections(db: Database) -> list[str]:
    return sorted(
        name
        for name in db.list_collection_names()
        if name not in _SKIPPED and not name.startswith("system.")
    )


def _colliding_ids(db: Database, name: str, symbol: str) -> list[Any]:
    """Return ids of ``symbol`` docs whose ``:BINANCE`` twin already exists under the unique key."""
    keys = UNIQUE_KEYS[name]
    let = {f"k{i}": f"${field}" for i, field in enumerate(keys)}
    match = [{"$eq": ["$symbol", _target(symbol)]}]
    match += [{"$eq": [f"${field}", f"$$k{i}"]} for i, field in enumerate(keys)]
    pipeline = [
        {"$match": {"symbol": symbol}},
        {
            "$lookup": {
                "from": name,
                "let": let,
                "pipeline": [
                    {"$match": {"$expr": {"$and": match}}},
                    {"$limit": 1},
                    {"$project": {"_id": 1}},
                ],
                "as": "twin",
            }
        },
        {"$match": {"twin.0": {"$exists": True}}},
        {"$project": {"_id": 1}},
    ]
    return [doc["_id"] for doc in db[name].aggregate(pipeline)]


def inventory(db: Database) -> dict:
    collections: dict[str, dict[str, int]] = {}
    for name in _collections(db):
        okx_docs = db[name].count_documents(_OKX)
        binance_docs = db[name].count_documents(_BINANCE)
        if not okx_docs and not binance_docs:
            continue
        collisions = 0
        if name in UNIQUE_KEYS:
            collisions = sum(
                len(_colliding_ids(db, name, s)) for s in db[name].distinct("symbol", _OKX)
            )
        collections[name] = {
            "okx_docs": okx_docs,
            "binance_docs": binance_docs,
            "collisions": collisions,
        }
    return {
        "collections": collections,
        "total_okx_docs": sum(c["okx_docs"] for c in collections.values()),
    }


def apply(db: Database) -> dict:
    result: dict[str, dict[str, int]] = {}
    for name in _collections(db):
        symbols = db[name].distinct("symbol", _OKX)
        if not symbols:
            continue
        renamed = dropped = 0
        for symbol in symbols:
            if name in UNIQUE_KEYS:
                ids = _colliding_ids(db, name, symbol)
                if ids:
                    dropped += db[name].delete_many({"_id": {"$in": ids}}).deleted_count
            update = db[name].update_many({"symbol": symbol}, {"$set": {"symbol": _target(symbol)}})
            renamed += update.modified_count
        result[name] = {"renamed": renamed, "dropped": dropped}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true", help="print the :OKX inventory")
    mode.add_argument("--apply", action="store_true", help="rename or drop :OKX documents")
    parser.add_argument("--approved", action="store_true", help="required with --apply")
    args = parser.parse_args(argv)

    if args.apply and not args.approved:
        print("refusing: --approved is required")
        return 2

    db = pymongo.MongoClient(os.environ["MONGODB_URL"])[os.environ["MONGODB_DATABASE"]]
    report = inventory(db) if args.inventory else apply(db)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
