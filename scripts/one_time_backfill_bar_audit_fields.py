"""One-shot: backfill updated_at + source for legacy bars.

Plan: plans/260523-0938-bar-audit-fields/phase-05-one-time-migration-script-deploy.md

Per doc lacking a `source` field:
  - $set source = "one_time_legacy"
  - $set updated_at = existing created_at (fallback datetime.now(UTC))

Idempotent — rerun is a no-op once complete (filter `$exists:false`).

Run inside the prod container:
    docker cp scripts/one_time_backfill_bar_audit_fields.py pocketquant-app:/tmp/
    docker exec pocketquant-app python /tmp/one_time_backfill_bar_audit_fields.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorClient
from pocketquant.core.common.constants import COLLECTION_BARS
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import SOURCE_ONE_TIME_LEGACY
from pymongo import UpdateOne

logger = get_logger("one_time_backfill_bar_audit_fields")

BATCH_SIZE = 1000
LOG_EVERY = 10_000


async def main() -> int:
    uri = os.environ.get("MONGODB_URI") or os.environ.get("MONGODB_URL")
    db_name = os.environ.get("MONGODB_DB") or os.environ.get("MONGODB_DATABASE", "pocketquant")
    if not uri:
        logger.error("migration.missing_mongodb_uri")
        return 2

    client = AsyncIOMotorClient(uri)
    collection = client[db_name][COLLECTION_BARS]

    total_matched = await collection.count_documents({"source": {"$exists": False}})
    logger.info("migration.started", total_to_update=total_matched, db=db_name)

    if total_matched == 0:
        logger.info("migration.no_work")
        return 0

    cursor = collection.find(
        {"source": {"$exists": False}},
        {"_id": 1, "created_at": 1},
        no_cursor_timeout=True,
        batch_size=BATCH_SIZE,
    )

    started = datetime.now(UTC)
    ops: list[UpdateOne] = []
    processed = 0
    updated = 0

    try:
        async for doc in cursor:
            ts = doc.get("created_at") or datetime.now(UTC)
            ops.append(
                UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": {"updated_at": ts, "source": SOURCE_ONE_TIME_LEGACY}},
                )
            )
            processed += 1

            if len(ops) >= BATCH_SIZE:
                result = await collection.bulk_write(ops, ordered=False)
                updated += result.modified_count
                ops = []

            if processed % LOG_EVERY == 0:
                logger.info(
                    "migration.progress",
                    processed=processed, updated=updated, total=total_matched,
                )

        if ops:
            result = await collection.bulk_write(ops, ordered=False)
            updated += result.modified_count
    finally:
        await cursor.close()

    duration = (datetime.now(UTC) - started).total_seconds()
    logger.info(
        "migration.completed",
        processed=processed,
        updated=updated,
        total=total_matched,
        duration_sec=round(duration, 2),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
