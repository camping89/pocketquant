# Guards two prod-only bug classes. A sparse=True unique index treats null as a value, so
# legacy docs with scheduled_run_time=null collide on index build. pymongo 4.16
# AsyncCollection.aggregate() is a coroutine resolving to a cursor; a caller that does not
# await it before async for raises TypeError.

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


# Wrapper-written rows carry scheduled_run_time=null; partialFilterExpression keeps them out
# of the unique index.
@pytest.mark.asyncio
async def test_idempotency_index_tolerates_legacy_null_rows(repo):
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


# BSON stores milliseconds, so a fast job can write two runs whose started_at compare equal,
# and sorting on that alone leaves $first free to return either. The rows are written
# directly so the tie is reproduced on purpose; it surfaced as an intermittent failure three
# times before it was pinned.
@pytest.mark.asyncio
async def test_latest_run_is_decided_when_two_runs_share_a_started_at(repo):
    shared = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
    # UUIDv7 is monotonic within a millisecond, so the greater id is the later
    # run. Inserted oldest-first on purpose: with equal started_at values the
    # sort is otherwise free to keep insertion order, which would hand $first
    # the WRONG row. Reverse this order and the test stops proving anything.
    older, newer = "0196c0de-0000-7000-8000-00000000000a", "0196c0de-0000-7000-8000-00000000000b"
    await repo._collection().insert_many(
        [
            {
                "_id": older,
                "job_id": "sync_5m",
                "started_at": shared,
                "status": "completed",
                "duration_ms": 100,
                "finished_at": shared,
                "error": None,
            },
            {
                "_id": newer,
                "job_id": "sync_5m",
                "started_at": shared,
                "status": "completed",
                "duration_ms": 200,
                "finished_at": shared,
                "error": None,
            },
        ]
    )

    result = await repo.get_latest_by_job_ids(["sync_5m"])

    assert result["sync_5m"]["duration_ms"] == 200


@pytest.mark.asyncio
async def test_record_detail_appends_to_run(repo):
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
async def test_interrupt_orphan_running_flips_every_running_row(repo):
    now = datetime.now(UTC)
    coll = repo._collection()
    await coll.insert_many(
        [
            {
                "_id": "recent",
                "job_id": "sync_repair",
                "status": "running",
                "started_at": now - timedelta(seconds=30),
            },
            {
                "_id": "old",
                "job_id": "sync_1m",
                "status": "running",
                "started_at": now - timedelta(minutes=15),
            },
            {
                "_id": "completed",
                "job_id": "sync_repair",
                "status": "completed",
                "started_at": now - timedelta(hours=1),
            },
        ]
    )

    assert await repo.interrupt_orphan_running() == 2

    for doc_id in ("recent", "old"):
        doc = await coll.find_one({"_id": doc_id})
        assert doc["status"] == "interrupted"
        assert doc["error"] == "orphan_running_recovered"
        assert doc["finished_at"] is not None
    assert (await coll.find_one({"_id": "completed"}))["status"] == "completed"


@pytest.mark.asyncio
async def test_resume_interrupted_claims_the_newest_cut_run_once(repo):
    now = datetime.now(UTC)
    coll = repo._collection()
    await coll.insert_many(
        [
            {
                "_id": "too_old",
                "job_id": "sync_repair",
                "status": "interrupted",
                "started_at": now - timedelta(hours=20),
                "done_symbols": ["A"],
            },
            {
                "_id": "cut",
                "job_id": "sync_repair",
                "status": "interrupted",
                "started_at": now - timedelta(minutes=3),
                "done_symbols": ["A", "B"],
            },
        ]
    )

    assert await repo.has_interrupted("sync_repair", now - timedelta(hours=12)) is True
    claimed = await repo.resume_interrupted("sync_repair", now - timedelta(hours=12))
    assert claimed is not None
    run_id, done = claimed
    assert done == {"A", "B"}
    cut = await coll.find_one({"_id": "cut"})
    assert (cut["status"], cut["run_id"]) == ("running", run_id)
    old = await coll.find_one({"_id": "too_old"})
    assert (old["status"], old["error"]) == ("failed", "superseded")
    assert await repo.resume_interrupted("sync_repair", now - timedelta(hours=24)) is None
    assert await repo.has_interrupted("sync_repair", now - timedelta(hours=24)) is False


# A stopped process that writes late still holds the old run id; once the row is
# resumed under a new one, those writes change nothing.
@pytest.mark.asyncio
async def test_a_late_write_under_the_old_run_id_misses_a_resumed_row(repo):
    old_run = await repo.record_start("sync_backfill")
    await repo.mark_symbol_done(old_run, "A")
    await repo.mark_symbol_done(old_run, "A")
    await repo.record_finish(old_run, status="interrupted")
    claimed = await repo.resume_interrupted("sync_backfill", datetime.now(UTC) - timedelta(hours=1))
    assert claimed is not None
    new_run, done = claimed
    assert done == {"A"}

    await repo.record_finish(old_run, status="completed")
    await repo.mark_symbol_done(old_run, "B")
    doc = await repo._collection().find_one({"_id": old_run})
    assert (doc["status"], doc["done_symbols"]) == ("running", ["A"])

    await repo.mark_symbol_done(new_run, "B")
    await repo.record_finish(new_run, status="completed", total_inserted=2)
    doc = await repo._collection().find_one({"_id": old_run})
    assert (doc["status"], doc["done_symbols"], doc["total_inserted"]) == (
        "completed",
        ["A", "B"],
        2,
    )


@pytest.mark.asyncio
async def test_get_last_successful_started_at_returns_latest_completed(repo):
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
    result = await repo.get_last_successful_started_at("never_ran")
    assert result is None
