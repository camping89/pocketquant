"""Integration tests for BacktestRepository.mark_orphaned_started_as_failed.

Single-worker boot sweep: every run still ``started`` is an orphan from a killed
task and must be flipped to ``failed`` (no age threshold — there is no legitimate
in-flight run across a restart).
"""

from __future__ import annotations

import pytest

from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def repo(settings):
    db = Database()
    await db.connect(settings)
    await db.get_collection(BacktestRepository._collection_name).drop()
    r = BacktestRepository(db)
    await r.ensure_indexes()
    yield r
    await db.disconnect()


async def _insert(repo: BacktestRepository, run_id: str, status: str) -> None:
    await repo._collection().insert_one(
        {"_id": run_id, "strategy_code": "strat-test", "status": status}
    )


@pytest.mark.asyncio
async def test_started_doc_is_marked_failed(repo):
    await _insert(repo, "run-orphan", status="started")

    count = await repo.mark_orphaned_started_as_failed()
    assert count == 1

    doc = await repo._collection().find_one({"_id": "run-orphan"})
    assert doc is not None
    assert doc["status"] == "failed"
    assert doc["error_message"] == "interrupted_by_restart"


@pytest.mark.asyncio
async def test_sweep_is_idempotent(repo):
    await _insert(repo, "run-idem", status="started")

    assert await repo.mark_orphaned_started_as_failed() == 1
    assert await repo.mark_orphaned_started_as_failed() == 0


@pytest.mark.asyncio
async def test_finished_and_failed_docs_untouched(repo):
    await _insert(repo, "run-finished", status="finished")
    await _insert(repo, "run-failed", status="failed")
    await _insert(repo, "run-started", status="started")

    count = await repo.mark_orphaned_started_as_failed()
    assert count == 1

    coll = repo._collection()
    assert (await coll.find_one({"_id": "run-finished"}))["status"] == "finished"
    assert (await coll.find_one({"_id": "run-failed"}))["status"] == "failed"
    assert (await coll.find_one({"_id": "run-started"}))["status"] == "failed"
