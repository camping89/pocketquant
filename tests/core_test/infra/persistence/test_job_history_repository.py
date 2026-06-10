"""Integration tests for JobHistoryRepository — guards two prod-only bug classes.

Bug class #1 — `sparse=True` unique index treats `null` as a value, so legacy
docs with `scheduled_run_time=null` collide on index build.
Guard: `record_skip` must coexist with `record_start`-written rows; index build
must succeed even when many `null` rows already exist.

Bug class #2 — pymongo 4.16 `AsyncCollection.aggregate()` returns a coroutine
that resolves to a cursor; callers MUST `await` before `async for`.
Guard: every aggregate-using method (`get_latest_by_job_ids`, `aggregate_stats`)
must run end-to-end against a real Mongo and return data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def repo(settings):
    db = Database()
    await db.connect(settings)
    # Fresh collection per test — drop, build indexes, hand off.
    await db.get_collection(JobHistoryRepository._collection_name).drop()
    r = JobHistoryRepository(db)
    await r.ensure_indexes()
    yield r
    await db.disconnect()


@pytest.mark.asyncio
async def test_idempotency_index_tolerates_legacy_null_rows(repo):
    """Multiple wrapper-written rows have scheduled_run_time=null. They must
    NOT trigger the unique constraint (partialFilterExpression filters them
    out). Regression for bug #1: previously sparse=True, which treats null as
    a value and crashed index build."""
    # Wrapper-path inserts (null scheduled_run_time) — many per job_id.
    for _ in range(5):
        await repo.record_start("sync_5m")
    for _ in range(3):
        await repo.record_start("sync_15m")

    # Re-running ensure_indexes must succeed (index already exists, no rebuild
    # collision). This was the failure mode in production.
    await repo.ensure_indexes()

    # Listener-path inserts (date scheduled_run_time) — second call with same
    # key must be a no-op (idempotent upsert).
    sched = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
    await repo.record_skip(job_id="sync_5m", scheduled_run_time=sched, status="missed")
    await repo.record_skip(job_id="sync_5m", scheduled_run_time=sched, status="missed")
    coll = repo._collection()
    rows = await coll.count_documents({"job_id": "sync_5m", "scheduled_run_time": sched})
    assert rows == 1, "record_skip must be idempotent on (job_id, scheduled_run_time)"


@pytest.mark.asyncio
async def test_get_latest_by_job_ids_awaits_aggregate(repo):
    """Regression for bug #2: `aggregate()` is a coroutine in pymongo 4.16.
    If it isn't awaited, `async for` raises TypeError. This test exercises
    the real cursor path — would have caught the bug before deploy."""
    now = datetime.now(UTC)
    doc_id_old = await repo.record_start("sync_5m")
    await repo.record_finish(doc_id_old, status="completed", duration_ms=100)
    doc_id_new = await repo.record_start("sync_5m")
    await repo.record_finish(doc_id_new, status="completed", duration_ms=200)

    result = await repo.get_latest_by_job_ids(["sync_5m", "sync_15m"])
    assert "sync_5m" in result
    assert result["sync_5m"]["status"] == "completed"
    # Newer doc must win (most-recent started_at).
    assert result["sync_5m"]["duration_ms"] == 200
    assert "sync_15m" not in result  # no rows for that job_id

    # Window: last 24h
    since = now - timedelta(hours=24)
    stats = await repo.aggregate_stats("sync_5m", since)
    assert stats["by_status"].get("completed") == 2
    # p50/p95 may be None on Mongo <7 but must not raise.
    assert "p50_ms" in stats and "p95_ms" in stats


@pytest.mark.asyncio
async def test_record_detail_appends_to_run(repo):
    """Smoke: per-(symbol, interval) detail records flow into details[]."""
    doc_id = await repo.record_start("sync_5m")
    await repo.record_detail(
        doc_id,
        symbol="BINANCE:BTCUSDT",
        interval="5m",
        bars_fetched=60,
        bars_inserted=3,
        filtered_existing=54,
        filtered_misaligned=0,
        status="completed",
    )
    runs = await repo.find_runs("sync_5m", limit=10)
    assert len(runs) == 1
    assert len(runs[0]["details"]) == 1
    d = runs[0]["details"][0]
    assert d["symbol"] == "BINANCE:BTCUSDT"
    assert d["bars_fetched"] == 60
    assert d["bars_inserted"] == 3


@pytest.mark.asyncio
async def test_reconcile_orphan_running_flips_only_stale_running(repo):
    """Only docs with status='running' AND started_at < cutoff are flipped.

    Guards against false positives:
      - recent 'running' doc (within grace) MUST stay running
      - already-'completed' doc MUST be left untouched
      - stale 'running' doc MUST flip to failed + error='orphan_running_recovered'
    """
    now = datetime.now(UTC)
    coll = repo._collection()
    await coll.insert_many(
        [
            # Recent running — within grace, must NOT flip.
            {
                "_id": "recent_running",
                "job_id": "sync_5m",
                "status": "running",
                "started_at": now - timedelta(seconds=30),
            },
            # Stale running — must flip.
            {
                "_id": "stale_running",
                "job_id": "sync_5m",
                "status": "running",
                "started_at": now - timedelta(minutes=15),
            },
            # Completed — must be left untouched (filter excludes it).
            {
                "_id": "completed",
                "job_id": "sync_5m",
                "status": "completed",
                "started_at": now - timedelta(hours=1),
            },
        ]
    )

    n = await repo.reconcile_orphan_running(max_age_seconds=600)
    assert n == 1

    stale = await coll.find_one({"_id": "stale_running"})
    assert stale["status"] == "failed"
    assert stale["error"] == "orphan_running_recovered"
    assert stale["finished_at"] is not None

    # Negative-control: recent + completed docs untouched.
    recent = await coll.find_one({"_id": "recent_running"})
    assert recent["status"] == "running"
    done = await coll.find_one({"_id": "completed"})
    assert done["status"] == "completed"


@pytest.mark.asyncio
async def test_get_last_successful_started_at_returns_latest_completed(repo):
    """Most-recent completed row wins. Non-completed statuses are ignored."""
    now = datetime.now(UTC)
    older_success = now - timedelta(days=2)
    recent_success = now - timedelta(hours=1)
    coll = repo._collection()
    await coll.insert_many(
        [
            {
                "_id": "a",
                "job_id": "sync_backfill",
                "status": "completed",
                "started_at": older_success,
            },
            {
                "_id": "b",
                "job_id": "sync_backfill",
                "status": "completed",
                "started_at": recent_success,
            },
            # 'failed' rows must be ignored even when newer than any success.
            {
                "_id": "c",
                "job_id": "sync_backfill",
                "status": "failed",
                "started_at": now - timedelta(minutes=5),
            },
            # 'running' rows must also be ignored.
            {
                "_id": "d",
                "job_id": "sync_backfill",
                "status": "running",
                "started_at": now - timedelta(minutes=1),
            },
        ]
    )

    result = await repo.get_last_successful_started_at("sync_backfill")
    assert result is not None
    # Mongo stores ms-precision; compare with 1s tolerance.
    assert abs((result - recent_success).total_seconds()) < 1


@pytest.mark.asyncio
async def test_get_last_successful_started_at_returns_none_for_no_history(repo):
    """Fresh DB / no successful run yet → None so caller skips catch-up."""
    result = await repo.get_last_successful_started_at("never_ran")
    assert result is None
