"""One-time migration: composite ``config_snapshot.symbol`` in backtest/optimization docs.

Older backtest_runs and optimization_runs documents persisted strategy config
as ``config_snapshot: {symbol: "BTCUSDT", exchange: "BINANCE", ...}``. After the
composite-symbol refactor, new runs persist ``config_snapshot.symbol`` as
``"BTCUSDT:BINANCE"`` and omit ``exchange``. This script consolidates pre-refactor
docs in place.

Idempotent: docs whose ``config_snapshot.symbol`` is already composite are skipped
(unset of any stale ``config_snapshot.exchange`` is still applied).

Usage:
    python -m scripts.one_time_consolidate_config_snapshot_symbol --dry-run
    python -m scripts.one_time_consolidate_config_snapshot_symbol --collection backtest_runs
    python -m scripts.one_time_consolidate_config_snapshot_symbol  # all targets, write mode
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from dataclasses import dataclass

from pymongo import UpdateOne
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.mongo_client import AsyncMongoClient

COMPOSITE_RE = re.compile(r"^[A-Z0-9._-]+:[A-Z0-9._-]+$")

TARGET_COLLECTIONS: tuple[str, ...] = ("backtest_runs", "optimization_runs")


@dataclass
class CollectionResult:
    name: str
    total: int
    skipped: int
    updated: int


def _build_composite(raw_symbol: str, exchange: str) -> str:
    """Compose ``{CODE}:{EXCHANGE}`` with uppercase normalisation."""
    return f"{raw_symbol.upper()}:{exchange.upper()}"


async def _migrate(coll: AsyncCollection, batch_size: int, dry_run: bool) -> CollectionResult:
    """Walk every doc, rewrite ``config_snapshot.symbol`` + drop ``config_snapshot.exchange``."""
    total = await coll.count_documents({})
    skipped = updated = 0
    batch: list[UpdateOne] = []

    cursor = coll.find({}, no_cursor_timeout=True)
    try:
        async for doc in cursor:
            snap = doc.get("config_snapshot") or {}
            if not isinstance(snap, dict):
                skipped += 1
                continue

            sym_raw = snap.get("symbol")
            exch = snap.get("exchange")

            if isinstance(sym_raw, str) and COMPOSITE_RE.match(sym_raw):
                # Already composite — only clean up stale exchange if present.
                if exch is not None:
                    batch.append(
                        UpdateOne(
                            {"_id": doc["_id"]},
                            {"$unset": {"config_snapshot.exchange": ""}},
                        )
                    )
                else:
                    skipped += 1
                    continue
            else:
                if not sym_raw or not exch:
                    print(
                        f"WARN  {coll.name}/{doc.get('_id')}: missing config_snapshot symbol or exchange; skipping",
                        file=sys.stderr,
                    )
                    skipped += 1
                    continue
                composite = _build_composite(str(sym_raw), str(exch))
                batch.append(
                    UpdateOne(
                        {"_id": doc["_id"]},
                        {
                            "$set": {"config_snapshot.symbol": composite},
                            "$unset": {"config_snapshot.exchange": ""},
                        },
                    )
                )

            if len(batch) >= batch_size:
                if not dry_run:
                    await coll.bulk_write(batch, ordered=False)
                updated += len(batch)
                batch = []

        if batch:
            if not dry_run:
                await coll.bulk_write(batch, ordered=False)
            updated += len(batch)

    finally:
        await cursor.close()

    return CollectionResult(name=coll.name, total=total, skipped=skipped, updated=updated)


async def _residual_count(coll: AsyncCollection) -> int:
    """Count docs still holding the legacy `config_snapshot.exchange` field."""
    return await coll.count_documents({"config_snapshot.exchange": {"$exists": True}})


async def run(
    mongo_uri: str,
    db_name: str,
    collections: tuple[str, ...],
    batch_size: int,
    dry_run: bool,
) -> list[CollectionResult]:
    client = AsyncMongoClient(mongo_uri)
    try:
        db = client[db_name]
        results: list[CollectionResult] = []
        for name in collections:
            print(f"\n=== {name} ===")
            coll = db[name]
            result = await _migrate(coll, batch_size=batch_size, dry_run=dry_run)
            residual = await _residual_count(coll)
            print(
                f"  total={result.total} skipped={result.skipped} updated={result.updated} "
                f"residual_with_exchange_field={residual} dry_run={dry_run}"
            )
            results.append(result)
        return results
    finally:
        await client.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGODB_URL"))
    parser.add_argument("--db-name", default=os.environ.get("MONGODB_DATABASE", "pocketquant"))
    parser.add_argument(
        "--collection",
        choices=TARGET_COLLECTIONS,
        default=None,
        help="Limit migration to one collection (default: all).",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not args.mongo_uri:
        print("ERROR: --mongo-uri or MONGODB_URL env var is required.", file=sys.stderr)
        sys.exit(2)

    collections = (args.collection,) if args.collection else TARGET_COLLECTIONS

    asyncio.run(
        run(
            mongo_uri=args.mongo_uri,
            db_name=args.db_name,
            collections=collections,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
