"""One-time cleanup: purge MongoDB data for deleted ``ma_crossover`` and ``hit_and_run`` strategies.

After replacing both legacy strategies with ``hitnrun2``, any orders / positions /
backtests / subscriptions still tagged with the old strategy IDs are orphans —
no code can resolve their ``strategy_id`` against ``STRATEGY_REGISTRY`` anymore.

This script deletes those orphan documents across all impacted collections.
Idempotent. Safe to re-run. Designed for the CD pipeline on VPS deploy.

Usage:
    python -m scripts.one_time_purge_legacy_strategies --dry-run
    python -m scripts.one_time_purge_legacy_strategies                # write mode
    python -m scripts.one_time_purge_legacy_strategies --strategy ma_crossover
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass

from pymongo.asynchronous.mongo_client import AsyncMongoClient

LEGACY_STRATEGY_IDS: tuple[str, ...] = ("ma_crossover", "hit_and_run")

# Collections that store ``strategy_id`` directly.
COLLECTIONS_WITH_STRATEGY_ID: tuple[str, ...] = (
    "orders",
    "positions",
    "backtest_runs",
    "optimization_runs",
    "strategy_subscriptions",
)


@dataclass
class PurgeResult:
    collection: str
    strategy_id: str
    matched: int
    deleted: int


async def purge_collection(
    db, collection_name: str, strategy_id: str, dry_run: bool
) -> PurgeResult:
    coll = db[collection_name]
    matched = await coll.count_documents({"strategy_id": strategy_id})
    deleted = 0
    if matched > 0 and not dry_run:
        res = await coll.delete_many({"strategy_id": strategy_id})
        deleted = res.deleted_count
    return PurgeResult(
        collection=collection_name,
        strategy_id=strategy_id,
        matched=matched,
        deleted=deleted,
    )


async def main_async(args: argparse.Namespace) -> int:
    mongo_uri = args.mongo_uri or os.environ.get("MONGODB_URL") or os.environ.get("MONGO_URI")
    db_name = args.db_name or os.environ.get("MONGODB_DATABASE") or os.environ.get("MONGO_DB") or "pocketquant"

    if not mongo_uri:
        print("ERROR  set --mongo-uri or MONGODB_URL env var", file=sys.stderr)
        return 2

    targets = (args.strategy,) if args.strategy else LEGACY_STRATEGY_IDS
    print(f"Connecting to: {mongo_uri} / db={db_name}")
    print(f"Dry run: {args.dry_run}")
    print(f"Targets: {list(targets)}")
    print(f"Collections: {list(COLLECTIONS_WITH_STRATEGY_ID)}")

    client = AsyncMongoClient(mongo_uri)
    try:
        db = client[db_name]
        results: list[PurgeResult] = []
        for strategy_id in targets:
            print(f"\n=== strategy_id={strategy_id} ===")
            for coll_name in COLLECTIONS_WITH_STRATEGY_ID:
                try:
                    r = await purge_collection(db, coll_name, strategy_id, args.dry_run)
                    results.append(r)
                    verb = "would delete" if args.dry_run else "deleted"
                    print(f"  {coll_name:30}  matched={r.matched:>6}  {verb}={r.deleted:>6}")
                except Exception as e:
                    print(f"  ERROR  {coll_name}/{strategy_id}: {e}", file=sys.stderr)
                    return 1

        total_matched = sum(r.matched for r in results)
        total_deleted = sum(r.deleted for r in results)
        print("\n=== Summary ===")
        print(f"  total_matched={total_matched}  total_deleted={total_deleted}  dry_run={args.dry_run}")
        if total_matched == 0:
            print("  (no legacy data found — nothing to purge)")
    finally:
        await client.close()

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Purge MongoDB data for deleted legacy strategies (ma_crossover, hit_and_run)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Read-only; log intended deletes")
    parser.add_argument(
        "--strategy",
        default=None,
        choices=list(LEGACY_STRATEGY_IDS),
        help="Limit to a single legacy strategy id (default: all)",
    )
    parser.add_argument("--mongo-uri", default=None, help="Override MONGODB_URL env var")
    parser.add_argument("--db-name", default=None, help="Override MONGODB_DATABASE env var")

    args = parser.parse_args()
    rc = asyncio.run(main_async(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
