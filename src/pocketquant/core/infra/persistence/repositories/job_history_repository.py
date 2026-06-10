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

from datetime import UTC, datetime, timedelta
from typing import Any

from pocketquant.core.common.constants import COLLECTION_JOB_HISTORY
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time import coerce_utc, to_utc_iso
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.infra.persistence.base_repository import BaseRepository

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
        interval: str,
        bars_fetched: int,
        bars_inserted: int,
        filtered_existing: int,
        filtered_misaligned: int,
        status: str,
        error: str | None = None,
    ) -> None:
        """Append a per-(symbol, interval) detail to the parent run doc.

        ``symbol`` is composite ``{code}:{exchange}``.
        """
        await self._collection().update_one(
            {"_id": doc_id},
            {
                "$push": {
                    "details": {
                        "symbol": symbol,
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

    async def reconcile_orphan_running(self, max_age_seconds: int = 600) -> int:
        """Flip stale ``status="running"`` docs to ``"failed"`` on startup.

        Orphan rows arise when a job's wrapper writes ``record_start()`` but the
        process is killed before ``record_finish()`` runs (e.g. mid-deploy
        CancelledError). Without this sweep, dashboards show forever-running jobs.

        Filter is ``status="running" AND started_at < now - max_age_seconds`` so
        a wrapper that legitimately completes mid-reconcile is safe: its
        ``record_finish()`` writes against ``_id`` (not status), and the doc is
        already excluded from this filter once status flips to ``completed``.

        Returns count of docs updated.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=max_age_seconds)
        result = await self._collection().update_many(
            {"status": "running", "started_at": {"$lt": cutoff}},
            {
                "$set": {
                    "status": "failed",
                    "finished_at": datetime.now(UTC),
                    "error": "orphan_running_recovered",
                }
            },
        )
        return result.modified_count

    async def get_last_successful_started_at(self, job_id: str) -> datetime | None:
        """Return ``started_at`` of the most recent ``completed`` run for ``job_id``.

        Used by startup catch-up logic to decide whether the gap since the last
        success exceeds the per-job cadence. Returns ``None`` if the job has no
        successful history (e.g. fresh DB) — caller should treat as "no catch-up
        needed" and let the next cron tick handle it.

        ``coerce_utc`` wrap: motor returns naive datetimes from Mongo. The caller
        in ``enqueue_missed_catchups`` subtracts against ``datetime.now(UTC)``,
        which raises ``TypeError: can't subtract offset-naive and offset-aware
        datetimes`` without this coercion.
        """
        doc = await self._collection().find_one(
            {"job_id": job_id, "status": "completed"},
            sort=[("started_at", -1)],
            projection={"started_at": 1},
        )
        return coerce_utc(doc["started_at"]) if doc else None

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
        cursor = await self._collection().aggregate(pipeline)
        async for row in cursor:
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

        cursor = self._collection().find(q).sort("started_at", -1).skip(offset).limit(limit)
        rows: list[dict[str, Any]] = []
        async for d in cursor:
            rows.append(_serialize(d))
        return rows

    async def aggregate_stats(self, job_id: str, since: datetime) -> dict[str, Any]:
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
        count_cursor = await coll.aggregate(count_pipeline)
        async for row in count_cursor:
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
            pct_cursor = await coll.aggregate(pct_pipeline)
            async for row in pct_cursor:
                p50_ms = row.get("p50")
                p95_arr = row.get("p95")
                # $percentile yields a single-element array; older fallbacks may yield a scalar.
                if isinstance(p95_arr, list):
                    p95_ms = p95_arr[0] if p95_arr else None
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
        # Idempotency for listener-written rows. partialFilterExpression keeps
        # legacy + wrapper rows (which have scheduled_run_time=null/missing)
        # OUT of the unique constraint — sparse alone treats null as a value.
        try:
            existing = await coll.index_information()
        except Exception:
            existing = {}
        if "idx_skip_idempotency" in existing:
            try:
                await coll.drop_index("idx_skip_idempotency")
            except Exception:
                logger.warning("job_history.idempotency_drop_failed", exc_info=True)
        await coll.create_index(
            [("job_id", 1), ("scheduled_run_time", 1)],
            name="idx_skip_idempotency",
            unique=True,
            partialFilterExpression={"scheduled_run_time": {"$type": "date"}},
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
        "details": [{**d, "ts": to_utc_iso(d.get("ts"))} for d in doc.get("details", []) or []],
    }
