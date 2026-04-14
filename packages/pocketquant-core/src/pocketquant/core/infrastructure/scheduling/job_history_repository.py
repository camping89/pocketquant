"""MongoDB repository for job execution history."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pocketquant.core.common.constants import COLLECTION_JOB_HISTORY
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time import to_utc_iso
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.persistence.base_repository import BaseRepository

logger = get_logger(__name__)


class JobHistoryRepository(BaseRepository):
    """Stores job execution records with TTL auto-pruning."""

    _collection_name = COLLECTION_JOB_HISTORY

    async def record_start(self, job_id: str) -> str:
        """Insert a 'running' record. Returns doc _id."""
        doc_id = generate_id_str()
        await self._collection().insert_one(
            {
                "_id": doc_id,
                "job_id": job_id,
                "started_at": datetime.now(UTC),
                "finished_at": None,
                "duration_ms": None,
                "status": "running",
                "error": None,
            }
        )
        return doc_id

    async def record_finish(
        self,
        doc_id: str,
        *,
        status: str,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        """Update a running record with completion info."""
        finished_at = datetime.now(UTC)
        await self._collection().update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "finished_at": finished_at,
                    "duration_ms": duration_ms,
                    "status": status,
                    "error": error,
                }
            },
        )

    async def get_latest_by_job_ids(self, job_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Get the latest execution record per job_id. Returns {job_id: doc}."""
        if not job_ids:
            return {}

        pipeline = [
            {"$match": {"job_id": {"$in": job_ids}}},
            {"$sort": {"started_at": -1}},
            {"$group": {"_id": "$job_id", "doc": {"$first": "$$ROOT"}}},
        ]
        results: dict[str, dict[str, Any]] = {}
        async for row in self._collection().aggregate(pipeline):  # pyright: ignore[reportGeneralTypeIssues]
            doc = row["doc"]
            results[row["_id"]] = {
                "started_at": to_utc_iso(doc.get("started_at")),
                "finished_at": to_utc_iso(doc.get("finished_at")),
                "duration_ms": doc.get("duration_ms"),
                "status": doc.get("status"),
                "error": doc.get("error"),
            }
        return results

    async def ensure_indexes(self) -> None:
        """Create compound + TTL indexes."""
        coll = self._collection()
        await coll.create_index(
            [("job_id", 1), ("started_at", -1)],
            name="idx_job_started",
        )
        await coll.create_index(
            "started_at",
            name="idx_ttl_started",
            expireAfterSeconds=7 * 86400,  # 7-day TTL
        )
        logger.info("job_history.indexes_ensured")
