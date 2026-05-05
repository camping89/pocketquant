"""MongoDB repository for job execution history.

Two write paths:
  - Wrapper path (`record_start` + `record_finish`): keyed by generated UUID;
    used by sync_jobs._run_sync. Writes "running" → "completed"|"failed".
  - Listener path (`record_skip`): keyed by (job_id, scheduled_run_time);
    used by APScheduler EVENT_JOB_MISSED/MAX_INSTANCES/ERROR. Idempotent
    upsert so multi-instance races converge.

`details[]` capacity note: documents store per-(symbol, interval) sub-records
inline; threshold ~50 entries per doc (1 symbol × 5 intervals = 5/doc today).
Beyond that, split to a child collection — deferred follow-up.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pocketquant.core.common.constants import COLLECTION_JOB_HISTORY
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time import to_utc_iso
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.persistence.base_repository import BaseRepository

logger = get_logger(__name__)

# 30-day retention — long enough for weekly review without unbounded growth.
_TTL_SECONDS = 30 * 86400


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
                "details": [],
                "total_inserted": 0,
                "total_fetched": 0,
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
        total_inserted: int | None = None,
        total_fetched: int | None = None,
    ) -> None:
        """Update a running record with completion info."""
        finished_at = datetime.now(UTC)
        update: dict[str, Any] = {
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "status": status,
            "error": error,
        }
        if total_inserted is not None:
            update["total_inserted"] = total_inserted
        if total_fetched is not None:
            update["total_fetched"] = total_fetched
        await self._collection().update_one({"_id": doc_id}, {"$set": update})

    async def record_skip(
        self,
        *,
        job_id: str,
        scheduled_run_time: datetime,
        status: str,
        error: str | None = None,
    ) -> None:
        """Idempotent upsert keyed by (job_id, scheduled_run_time).
        Status: 'missed' | 'skipped_max_instances' | 'failed'."""
        await self._collection().update_one(
            {"job_id": job_id, "scheduled_run_time": scheduled_run_time},
            {
                "$setOnInsert": {
                    "_id": generate_id_str(),
                    "job_id": job_id,
                    "scheduled_run_time": scheduled_run_time,
                    "started_at": scheduled_run_time,
                    "finished_at": datetime.now(UTC),
                    "duration_ms": 0,
                    "status": status,
                    "error": error,
                    "details": [],
                    "total_inserted": 0,
                    "total_fetched": 0,
                }
            },
            upsert=True,
        )

    async def record_detail(
        self,
        doc_id: str,
        *,
        symbol: str,
        exchange: str,
        interval: str,
        bars_fetched: int,
        bars_inserted: int,
        filtered_existing: int,
        filtered_misaligned: int,
        status: str,
        error: str | None = None,
    ) -> None:
        """Append a per-(symbol, interval) detail to the parent run doc."""
        await self._collection().update_one(
            {"_id": doc_id},
            {
                "$push": {
                    "details": {
                        "symbol": symbol,
                        "exchange": exchange,
                        "interval": interval,
                        "bars_fetched": bars_fetched,
                        "bars_inserted": bars_inserted,
                        "filtered_existing": filtered_existing,
                        "filtered_misaligned": filtered_misaligned,
                        "status": status,
                        "error": error,
                        "ts": datetime.now(UTC),
                    }
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

    async def find_runs(
        self,
        job_id: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Paginated runs for a job, newest first."""
        q: dict[str, Any] = {"job_id": job_id}
        if since or until:
            range_q: dict[str, Any] = {}
            if since:
                range_q["$gte"] = since
            if until:
                range_q["$lte"] = until
            q["started_at"] = range_q
        if status:
            q["status"] = status

        cursor = (
            self._collection()
            .find(q)
            .sort("started_at", -1)
            .skip(offset)
            .limit(limit)
        )
        rows: list[dict[str, Any]] = []
        async for d in cursor:
            rows.append(_serialize(d))
        return rows

    async def aggregate_stats(
        self, job_id: str, since: datetime
    ) -> dict[str, Any]:
        """Counts by status + p50/p95 duration over [since, now].

        Uses Mongo 7+ `$median` / `$percentile`. Falls back gracefully if the
        operators aren't supported by returning counts only.
        """
        coll = self._collection()
        # Status counts (always available)
        count_pipeline: list[dict[str, Any]] = [
            {"$match": {"job_id": job_id, "started_at": {"$gte": since}}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        by_status: dict[str, int] = {}
        async for row in coll.aggregate(count_pipeline):  # pyright: ignore[reportGeneralTypeIssues]
            by_status[row["_id"]] = row["count"]

        p50_ms: float | None = None
        p95_ms: float | None = None
        try:
            pct_pipeline: list[dict[str, Any]] = [
                {
                    "$match": {
                        "job_id": job_id,
                        "started_at": {"$gte": since},
                        "duration_ms": {"$gt": 0},
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "p50": {
                            "$median": {
                                "input": "$duration_ms",
                                "method": "approximate",
                            }
                        },
                        "p95": {
                            "$percentile": {
                                "input": "$duration_ms",
                                "p": [0.95],
                                "method": "approximate",
                            }
                        },
                    }
                },
            ]
            async for row in coll.aggregate(pct_pipeline):  # pyright: ignore[reportGeneralTypeIssues]
                p50_ms = row.get("p50")
                p95_arr = row.get("p95")
                if isinstance(p95_arr, list) and p95_arr:
                    p95_ms = p95_arr[0]
                else:
                    p95_ms = p95_arr
        except Exception:
            # Older Mongo (<7) lacks $median/$percentile — skip gracefully.
            logger.warning("job_history.percentile_unavailable", exc_info=True)

        return {"by_status": by_status, "p50_ms": p50_ms, "p95_ms": p95_ms}

    async def ensure_indexes(self) -> None:
        """Create compound + TTL + idempotency indexes."""
        coll = self._collection()
        await coll.create_index(
            [("job_id", 1), ("started_at", -1)],
            name="idx_job_started",
        )
        # TTL: drop & recreate if expireAfterSeconds drifted.
        await self._ensure_ttl_index(coll)
        # Idempotency for listener-written rows. sparse=True: wrapper-written
        # rows have no scheduled_run_time, so they are excluded.
        await coll.create_index(
            [("job_id", 1), ("scheduled_run_time", 1)],
            name="idx_skip_idempotency",
            unique=True,
            sparse=True,
        )
        logger.info("job_history.indexes_ensured")

    async def _ensure_ttl_index(self, coll: Any) -> None:
        index_name = "idx_ttl_started"
        try:
            existing = await coll.index_information()
        except Exception:
            existing = {}
        info = existing.get(index_name) if isinstance(existing, dict) else None
        if info and info.get("expireAfterSeconds") != _TTL_SECONDS:
            try:
                await coll.drop_index(index_name)
            except Exception:
                logger.warning("job_history.ttl_drop_failed", exc_info=True)
        await coll.create_index(
            "started_at",
            name=index_name,
            expireAfterSeconds=_TTL_SECONDS,
        )


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe view of a run doc."""
    return {
        "_id": doc.get("_id"),
        "job_id": doc.get("job_id"),
        "started_at": to_utc_iso(doc.get("started_at")),
        "finished_at": to_utc_iso(doc.get("finished_at")),
        "scheduled_run_time": to_utc_iso(doc.get("scheduled_run_time")),
        "duration_ms": doc.get("duration_ms"),
        "status": doc.get("status"),
        "error": doc.get("error"),
        "total_inserted": doc.get("total_inserted"),
        "total_fetched": doc.get("total_fetched"),
        "details": [
            {**d, "ts": to_utc_iso(d.get("ts"))} for d in doc.get("details", []) or []
        ],
    }
