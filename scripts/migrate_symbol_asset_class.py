"""Stamp existing symbol documents with an explicit asset class and calendar.

Every symbol in Mongo predates the asset-class model and carries a free-string
``asset_type``. All of them are crypto spot on a 24/7 calendar with linear
contract units, so the migration is a single unconditional shape: set the three
new fields, drop the old one.

Documents that already have ``asset_class`` are left alone, which makes this
safe to re-run and safe to run before or after the deploy that introduces the
new ``Symbol`` shape — ``Symbol.from_mongo`` already defaults a missing field to
exactly the values written here.

Usage:
    uv run python scripts/migrate_symbol_asset_class.py [--apply]

Dry-run by default: prints how many documents would change and writes nothing.
``--apply`` performs the update.

Exit codes: 0 = completed (or dry run); 1 = a write failed; 2 = MONGODB_URL unset.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from pymongo import AsyncMongoClient

COLLECTION = "symbols"

MIGRATION = {
    "$set": {
        "asset_class": "crypto_spot",
        "calendar_id": "CRYPTO_24_7",
        "contract_spec": {
            "multiplier": 1.0,
            "tick_size": 0.0,
            "lot_step": None,
            "currency": "USD",
            "commission_per_contract": None,
        },
    },
    "$unset": {"asset_type": ""},
}

SELECTOR = {"asset_class": {"$exists": False}}


async def migrate(apply: bool) -> int:
    url = os.environ.get("MONGODB_URL")
    if not url:
        print("MONGODB_URL is not set", file=sys.stderr)
        return 2

    database_name = os.environ.get("MONGODB_DATABASE", "pocketquant")
    client: AsyncMongoClient = AsyncMongoClient(url, tz_aware=True)
    try:
        collection = client[database_name][COLLECTION]
        matched = await collection.count_documents(SELECTOR)
        total = await collection.count_documents({})
        print(f"{total} symbol document(s); {matched} without asset_class")

        if not apply:
            print("Dry run — nothing written. Re-run with --apply to migrate.")
            return 0

        if matched == 0:
            print("Nothing to migrate.")
            return 0

        result = await collection.update_many(SELECTOR, MIGRATION)
        print(f"matched={result.matched_count} modified={result.modified_count}")
        if result.modified_count != matched:
            print(
                f"Expected to modify {matched} document(s) but modified "
                f"{result.modified_count}",
                file=sys.stderr,
            )
            return 1
        return 0
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the update; without it the script only reports counts",
    )
    args = parser.parse_args()
    return asyncio.run(migrate(apply=args.apply))


if __name__ == "__main__":
    sys.exit(main())
