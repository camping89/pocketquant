"""Integration tests for BacktestRepository.mark_stale_running_as_failed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pocketquant.core.persistence.mongodb import Database
from pocketquant.core.persistence.repositories.backtest_repository import (
    BacktestRepository,
)

pytestmark = pytest.mark.integration


# Fixtures


@pytest.fixture
async def repo(settings):
    db = Database()
    await db.connect(settings)
    await db.get_collection(BacktestRepository._collection_name).drop()
    r = BacktestRepository(db)
    await r.ensure_indexes()
    yield r
    await db.disconnect()


# Helpers


async def _insert_running(repo: BacktestRepository, sub_id: str, age_minutes: float) -> None:
    """Directly insert a minimal 'running' doc into the backtest_runs collection."""
    collection = repo._collection()
    now = datetime.now(UTC)
    await collection.insert_one(
        {
            "_id": sub_id,
            "subscription_id": sub_id,
            "strategy_code": "strat-test",
            "status": "running",
            "last_run_at": now - timedelta(minutes=age_minutes),
        }
    )


# Tests


@pytest.mark.asyncio
async def test_stale_running_doc_is_marked_failed(repo):
    """Doc running for 30 min exceeds 10-min threshold → marked failed."""
    await _insert_running(repo, "sub-stale", age_minutes=30)

    count = await repo.mark_stale_running_as_failed(threshold_minutes=10)
    assert count == 1

    collection = repo._collection()
    doc = await collection.find_one({"_id": "sub-stale"})
    assert doc is not None
    assert doc["status"] == "failed"
    assert doc["error_msg"] == "stale_recovery"


@pytest.mark.asyncio
async def test_mark_stale_is_idempotent(repo):
    """Second call on already-failed doc returns 0 — no double-update."""
    await _insert_running(repo, "sub-idem", age_minutes=30)

    first = await repo.mark_stale_running_as_failed(threshold_minutes=10)
    assert first == 1

    second = await repo.mark_stale_running_as_failed(threshold_minutes=10)
    assert second == 0


@pytest.mark.asyncio
async def test_fresh_running_doc_is_not_touched(repo):
    """Doc running for 1 min is below threshold → not modified."""
    await _insert_running(repo, "sub-fresh", age_minutes=1)

    count = await repo.mark_stale_running_as_failed(threshold_minutes=10)
    assert count == 0

    collection = repo._collection()
    doc = await collection.find_one({"_id": "sub-fresh"})
    assert doc is not None
    assert doc["status"] == "running"


@pytest.mark.asyncio
async def test_only_stale_docs_affected_mixed_ages(repo):
    """Mixed-age docs: only stale ones are updated."""
    await _insert_running(repo, "sub-old-1", age_minutes=60)
    await _insert_running(repo, "sub-old-2", age_minutes=20)
    await _insert_running(repo, "sub-new-1", age_minutes=5)

    count = await repo.mark_stale_running_as_failed(threshold_minutes=10)
    assert count == 2

    collection = repo._collection()
    old1 = await collection.find_one({"_id": "sub-old-1"})
    old2 = await collection.find_one({"_id": "sub-old-2"})
    new1 = await collection.find_one({"_id": "sub-new-1"})

    assert old1["status"] == "failed"
    assert old2["status"] == "failed"
    assert new1["status"] == "running"
