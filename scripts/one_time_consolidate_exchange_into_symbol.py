"""One-time migration: consolidate (symbol, exchange) pair into composite ``{code}:{exchange}``.

Targets MongoDB collections: symbols, bars, sync_status, strategy_subscriptions,
tracked_symbols, orders, positions, strategies, backtest_runs, optimization_runs.

Idempotent. Re-running on already-migrated docs is a no-op. Drops old compound
indexes that reference `exchange` and creates new indexes on composite ``symbol``.

Usage:
    python -m scripts.one_time_consolidate_exchange_into_symbol --dry-run
    python -m scripts.one_time_consolidate_exchange_into_symbol --collection bars
    python -m scripts.one_time_consolidate_exchange_into_symbol --batch-size 2000
    python -m scripts.one_time_consolidate_exchange_into_symbol  # all collections, write mode
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

# Spec for each collection:
#   collection_name: name in Mongo
#   code_field:      legacy field that held the bare code (often "symbol")
#   exchange_field:  legacy field that held the exchange (always "exchange")
#   composite_field: target field for composite (always "symbol")
#   indexes_to_drop: list of legacy index names to drop pre-migration
#   indexes_to_create: list of (keys: list[tuple], options: dict) to create post-migration
@dataclass(frozen=True)
class CollectionSpec:
    name: str
    code_field: str
    exchange_field: str = "exchange"
    composite_field: str = "symbol"
    indexes_to_drop: tuple[str, ...] = ()
    indexes_to_create: tuple[tuple[list[tuple[str, int]], dict], ...] = ()


SPECS: dict[str, CollectionSpec] = {
    "symbols": CollectionSpec(
        name="symbols",
        code_field="symbol",  # bare-code field collided with composite name
        indexes_to_drop=(
            "ix_symbols_symbol_exchange",
            "symbol_1_exchange_1",
        ),
        indexes_to_create=(
            ([("symbol", 1)], {"unique": True, "name": "ix_symbols_symbol"}),
        ),
    ),
    "bars": CollectionSpec(
        name="bars",
        code_field="symbol",
        indexes_to_drop=(
            "ix_ohlcv_symbol_exchange_interval_datetime",
            "symbol_1_exchange_1_interval_1_datetime_1",
        ),
        indexes_to_create=(
            (
                [("symbol", 1), ("interval", 1), ("datetime", 1)],
                {"unique": True, "name": "ix_ohlcv_symbol_interval_datetime"},
            ),
        ),
    ),
    "sync_status": CollectionSpec(
        name="sync_status",
        code_field="symbol",
        indexes_to_drop=(
            "ix_sync_status_symbol_exchange_interval",
            "symbol_1_exchange_1_interval_1",
        ),
        indexes_to_create=(
            (
                [("symbol", 1), ("interval", 1)],
                {"unique": True, "name": "ix_sync_status_symbol_interval"},
            ),
        ),
    ),
    "strategy_subscriptions": CollectionSpec(
        name="strategy_subscriptions",
        code_field="symbol",
    ),
    "tracked_symbols": CollectionSpec(
        name="tracked_symbols",
        code_field="symbol",
        indexes_to_drop=(
            "ix_tracked_symbols_exchange_symbol",
            "exchange_1_symbol_1",
        ),
        indexes_to_create=(
            ([("symbol", 1)], {"unique": True, "name": "ix_tracked_symbols_symbol"}),
        ),
    ),
    "orders": CollectionSpec(
        name="orders",
        code_field="symbol",
        indexes_to_drop=(
            "ix_orders_symbol_exchange",
        ),
        indexes_to_create=(
            ([("symbol", 1)], {"name": "ix_orders_symbol"}),
        ),
    ),
    "positions": CollectionSpec(
        name="positions",
        code_field="symbol",
        indexes_to_drop=(
            "ix_positions_symbol_exchange",
        ),
        indexes_to_create=(
            ([("symbol", 1)], {"name": "ix_positions_symbol"}),
        ),
    ),
    "strategies": CollectionSpec(
        name="strategies",
        code_field="symbol",
    ),
    "backtest_runs": CollectionSpec(
        name="backtest_runs",
        code_field="symbol",
    ),
    "optimization_runs": CollectionSpec(
        name="optimization_runs",
        code_field="symbol",
    ),
}


@dataclass
class MigrationResult:
    collection: str
    total: int
    skipped: int
    updated: int
    indexes_dropped: list[str]
    indexes_created: list[str]


async def _drop_legacy_indexes(coll: AsyncCollection, names: tuple[str, ...], dry_run: bool) -> list[str]:
    """Drop legacy indexes by name. Safe-skips unknown names."""
    dropped: list[str] = []
    existing = await coll.index_information()
    for name in names:
        if name in existing:
            if not dry_run:
                await coll.drop_index(name)
            dropped.append(name)
    return dropped


async def _create_new_indexes(
    coll: AsyncCollection,
    specs: tuple[tuple[list[tuple[str, int]], dict], ...],
    dry_run: bool,
) -> list[str]:
    """Create new indexes per spec. Idempotent — Mongo no-ops if already present."""
    created: list[str] = []
    for keys, opts in specs:
        if not dry_run:
            await coll.create_index(keys, **opts)
        created.append(str(opts.get("name", keys)))
    return created


def _build_composite(raw_symbol: str, exchange: str) -> str:
    """Compose `{CODE}:{EXCHANGE}` with uppercase normalisation."""
    return f"{raw_symbol.upper()}:{exchange.upper()}"


async def _migrate_documents(
    coll: AsyncCollection,
    spec: CollectionSpec,
    batch_size: int,
    dry_run: bool,
) -> tuple[int, int, int]:
    """Iterate cursor, build UpdateOne batches, flush at batch_size.

    Returns (total, skipped, updated).
    """
    total = await coll.count_documents({})
    skipped = updated = 0
    batch: list[UpdateOne] = []

    cursor = coll.find({}, no_cursor_timeout=True)
    try:
        async for doc in cursor:
            sym_raw = doc.get(spec.composite_field)
            exch = doc.get(spec.exchange_field)

            # Already composite ?
            if isinstance(sym_raw, str) and COMPOSITE_RE.match(sym_raw):
                # If legacy exchange field still present, queue an $unset only.
                if exch is not None:
                    batch.append(
                        UpdateOne(
                            {"_id": doc["_id"]},
                            {"$unset": {spec.exchange_field: ""}},
                        )
                    )
                else:
                    skipped += 1
                    continue
            else:
                # Need to compose. Tolerate either (sym_raw=code, exch=exchange).
                if not sym_raw or not exch:
                    # Incomplete doc — skip with warning. Avoid raising mid-migration.
                    print(
                        f"WARN  {spec.name}/{doc.get('_id')}: missing symbol or exchange; skipping",
                        file=sys.stderr,
                    )
                    skipped += 1
                    continue
                composite = _build_composite(str(sym_raw), str(exch))
                batch.append(
                    UpdateOne(
                        {"_id": doc["_id"]},
                        {
                            "$set": {spec.composite_field: composite},
                            "$unset": {spec.exchange_field: ""},
                        },
                    )
                )

            if len(batch) >= batch_size:
                if not dry_run:
                    await coll.bulk_write(batch, ordered=False)
                updated += len(batch)
                batch = []
                if updated % (batch_size * 10) == 0:
                    print(f"  ... {spec.name}: {updated} migrated so far")

        if batch:
            if not dry_run:
                await coll.bulk_write(batch, ordered=False)
            updated += len(batch)

    finally:
        await cursor.close()

    return total, skipped, updated


async def migrate_collection(
    db,
    spec: CollectionSpec,
    batch_size: int,
    dry_run: bool,
) -> MigrationResult:
    coll = db[spec.name]
    print(f"\n=== {spec.name} ===")

    # 1. Drop legacy indexes first so writes don't conflict with stale unique constraints
    dropped = await _drop_legacy_indexes(coll, spec.indexes_to_drop, dry_run)
    if dropped:
        print(f"  dropped legacy indexes: {dropped}")

    # 2. Migrate documents
    total, skipped, updated = await _migrate_documents(coll, spec, batch_size, dry_run)
    print(f"  total={total} skipped={skipped} updated={updated} (dry_run={dry_run})")

    # 3. Verify: no doc should still carry the legacy `exchange` field
    residual = await coll.count_documents({spec.exchange_field: {"$exists": True}})
    if residual > 0:
        if dry_run:
            print(f"  [dry-run] {residual} docs would still have legacy '{spec.exchange_field}' field")
        else:
            print(f"  WARN  {residual} docs still have legacy '{spec.exchange_field}' field after migration", file=sys.stderr)

    # 4. Create new indexes (only if not dry run AND there were no residuals OR migration was a no-op)
    created = await _create_new_indexes(coll, spec.indexes_to_create, dry_run)
    if created:
        print(f"  created new indexes: {created}")

    return MigrationResult(
        collection=spec.name,
        total=total,
        skipped=skipped,
        updated=updated,
        indexes_dropped=dropped,
        indexes_created=created,
    )


async def main_async(args: argparse.Namespace) -> int:
    mongo_uri = args.mongo_uri or os.environ.get("MONGO_URI") or "mongodb://localhost:27017"
    db_name = args.db_name or os.environ.get("MONGO_DB") or "pocketquant"

    print(f"Connecting to: {mongo_uri} / db={db_name}")
    print(f"Dry run: {args.dry_run}")
    print(f"Batch size: {args.batch_size}")

    if args.collection == "all":
        targets = list(SPECS.values())
    else:
        if args.collection not in SPECS:
            print(f"Unknown collection: {args.collection}. Known: {list(SPECS)}", file=sys.stderr)
            return 2
        targets = [SPECS[args.collection]]

    client = AsyncMongoClient(mongo_uri)
    try:
        db = client[db_name]

        results: list[MigrationResult] = []
        for spec in targets:
            try:
                result = await migrate_collection(db, spec, args.batch_size, args.dry_run)
                results.append(result)
            except Exception as e:
                print(f"ERROR migrating {spec.name}: {e}", file=sys.stderr)
                return 1

        print("\n=== Summary ===")
        for r in results:
            print(
                f"  {r.collection:30}  total={r.total:>10}  updated={r.updated:>10}  skipped={r.skipped:>10}"
            )
    finally:
        await client.close()

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consolidate (symbol, exchange) pair into composite ``{code}:{exchange}`` field",
    )
    parser.add_argument("--dry-run", action="store_true", help="Read-only; log intended changes")
    parser.add_argument(
        "--collection",
        default="all",
        choices=[*SPECS.keys(), "all"],
        help="Limit to a single collection (default: all)",
    )
    parser.add_argument("--batch-size", type=int, default=1000, help="UpdateOne batch size (default: 1000)")
    parser.add_argument("--mongo-uri", default=None, help="Override MONGO_URI env var")
    parser.add_argument("--db-name", default=None, help="Override MONGO_DB env var")

    args = parser.parse_args()
    rc = asyncio.run(main_async(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
