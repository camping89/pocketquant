from __future__ import annotations

from datetime import UTC, datetime
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
    _collection_name = COLLECTION_JOB_HISTORY

    # Returns the run id. Every later write of this run filters on it, and a resume gives
    # the row a new one, so a late write from a stopped process changes nothing.
    async def record_start(self, job_id: str) -> str:
        doc_id = generate_id_str()
        await self._collection().insert_one(
            {
                "_id": doc_id,
                "run_id": doc_id,
                "job_id": job_id,
                "started_at": datetime.now(UTC),
                "finished_at": None,
                "duration_ms": None,
                "status": "running",
                "error": None,
                "details": [],
                "done_symbols": [],
                "total_inserted": 0,
                "total_fetched": 0,
            }
        )
        return doc_id

    async def record_finish(
        self,
        run_id: str,
        *,
        status: str,
        duration_ms: int | None = None,
        error: str | None = None,
        total_inserted: int | None = None,
        total_fetched: int | None = None,
    ) -> None:
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
        await self._collection().update_one({"run_id": run_id}, {"$set": update})

    async def mark_symbol_done(self, run_id: str, symbol: str) -> None:
        await self._collection().update_one(
            {"run_id": run_id}, {"$addToSet": {"done_symbols": symbol}}
        )

    # Claims the newest run a handover cut after `since` under a new run id, so the run
    # skips its finished symbols; every older cut run of the job is closed. Returns
    # (run_id, finished symbols) or None.
    async def resume_interrupted(self, job_id: str, since: datetime) -> tuple[str, set[str]] | None:
        run_id = generate_id_str()
        doc = await self._collection().find_one_and_update(
            {"job_id": job_id, "status": "interrupted", "started_at": {"$gte": since}},
            {"$set": {"run_id": run_id, "status": "running", "finished_at": None, "error": None}},
            sort=[("started_at", -1)],
            projection={"done_symbols": 1},
        )
        await self.close_interrupted(job_id)
        return (run_id, set(doc.get("done_symbols") or [])) if doc else None

    # A fresh run supersedes every cut run of the job, so a later resume cannot skip
    # symbols an older cycle finished.
    async def close_interrupted(self, job_id: str) -> None:
        await self._collection().update_many(
            {"job_id": job_id, "status": "interrupted"},
            {"$set": {"status": "failed", "error": "superseded"}},
        )

    async def has_interrupted(self, job_id: str, since: datetime) -> bool:
        doc = await self._collection().find_one(
            {"job_id": job_id, "status": "interrupted", "started_at": {"$gte": since}},
            projection={"_id": 1},
        )
        return doc is not None

    # Idempotent upsert keyed by (job_id, scheduled_run_time), so multi-instance races
    # converge.
    async def record_skip(
        self,
        *,
        job_id: str,
        scheduled_run_time: datetime,
        status: str,
        error: str | None = None,
    ) -> None:
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

    # details[] is stored inline on the run doc; that holds up to about 50 entries per doc.
    async def record_detail(
        self,
        run_id: str,
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
        await self._collection().update_one(
            {"run_id": run_id},
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

    # A process killed between record_start() and record_finish() leaves a running row.
    # Called by a worker that just took the lease, before its scheduler starts. A stopped
    # process that still writes uses its old run id, which a resume replaces.
    async def interrupt_orphan_running(self) -> int:
        result = await self._collection().update_many(
            {"status": "running"},
            {
                "$set": {
                    "status": "interrupted",
                    "finished_at": datetime.now(UTC),
                    "error": "orphan_running_recovered",
                }
            },
        )
        return result.modified_count

    # None (no successful run yet) means no catch-up; the next cron tick handles it.
    async def get_last_successful_started_at(self, job_id: str) -> datetime | None:
        doc = await self._collection().find_one(
            {"job_id": job_id, "status": "completed"},
            sort=[("started_at", -1)],
            projection={"started_at": 1},
        )
        return coerce_utc(doc["started_at"]) if doc else None

    async def get_latest_by_job_ids(self, job_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not job_ids:
            return {}

        pipeline = [
            {"$match": {"job_id": {"$in": job_ids}}},
            # `_id` breaks the tie when two runs of one job share a started_at.
            # BSON stores milliseconds, so two runs started inside the same
            # millisecond compare equal and `$first` would pick arbitrarily
            # between them. `_id` is a UUIDv7 string, monotonic within a
            # millisecond and lexicographically ordered by generation time, so
            # descending on it yields the later run deterministically.
            {"$sort": {"started_at": -1, "_id": -1}},
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

    # $median / $percentile need Mongo 7+; without them only the counts are returned.
    async def aggregate_stats(self, job_id: str, since: datetime) -> dict[str, Any]:
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

    async def remove_symbol_details(self, symbol: str) -> int:
        result = await self._collection().update_many(
            {"details.symbol": symbol}, {"$pull": {"details": {"symbol": symbol}}}
        )
        logger.info("job_history.symbol_details_removed", symbol=symbol, docs=result.modified_count)
        return result.modified_count

    async def ensure_indexes(self) -> None:
        coll = self._collection()
        await coll.create_index(
            [("job_id", 1), ("started_at", -1)],
            name="idx_job_started",
        )
        await coll.create_index([("run_id", 1)], name="idx_run_id")
        # TTL: drop & recreate if expireAfterSeconds drifted.
        await self._ensure_ttl_index(coll)
        # Idempotency for listener-written rows. partialFilterExpression keeps
        # legacy + wrapper rows (which have scheduled_run_time=null/missing)
        # OUT of the unique constraint — sparse alone treats null as a value.
        # Dropped only when its spec drifted: role containers start at once, and one
        # container's drop aborts another's index build.
        partial = {"scheduled_run_time": {"$type": "date"}}
        try:
            existing = await coll.index_information()
        except Exception:
            existing = {}
        current = existing.get("idx_skip_idempotency")
        if current and not (
            current.get("unique") and current.get("partialFilterExpression") == partial
        ):
            try:
                await coll.drop_index("idx_skip_idempotency")
            except Exception:
                logger.warning("job_history.idempotency_drop_failed", exc_info=True)
        await coll.create_index(
            [("job_id", 1), ("scheduled_run_time", 1)],
            name="idx_skip_idempotency",
            unique=True,
            partialFilterExpression=partial,
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
