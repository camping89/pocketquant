"""Integration tests for BacktestRepository.mark_orphaned_started_as_failed.

A ``started`` run is an orphan once its heartbeat is older than 60 s; a run with no
heartbeat yet falls back to ``started_at``. A live run refreshes every 15 s.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


def _ago(seconds: float) -> datetime:
    return datetime.now(UTC) - timedelta(seconds=seconds)


async def _insert(repo: BacktestRepository, run_id: str, status: str, **fields) -> None:
    await repo._collection().insert_one(
        {"_id": run_id, "strategy_code": "strat-test", "status": status, **fields}
    )


async def _status(repo: BacktestRepository, run_id: str) -> str:
    doc = await repo._collection().find_one({"_id": run_id})
    assert doc is not None
    return doc["status"]


async def test_stale_heartbeat_is_marked_failed(repo):
    await _insert(repo, "run-stale", "started", started_at=_ago(600), heartbeat_at=_ago(61))

    assert await repo.mark_orphaned_started_as_failed() == 1

    doc = await repo._collection().find_one({"_id": "run-stale"})
    assert doc is not None
    assert doc["status"] == "failed"
    assert doc["error_message"] == "interrupted_by_restart"


async def test_fresh_heartbeat_survives(repo):
    await _insert(repo, "run-live", "started", started_at=_ago(600), heartbeat_at=_ago(5))

    assert await repo.mark_orphaned_started_as_failed() == 0
    assert await _status(repo, "run-live") == "started"


async def test_missing_heartbeat_falls_back_to_started_at(repo):
    await _insert(repo, "run-old", "started", started_at=_ago(61))
    await _insert(repo, "run-new", "started", started_at=_ago(5))

    assert await repo.mark_orphaned_started_as_failed() == 1
    assert await _status(repo, "run-old") == "failed"
    assert await _status(repo, "run-new") == "started"


async def test_sweep_is_idempotent(repo):
    await _insert(repo, "run-idem", "started", heartbeat_at=_ago(61))

    assert await repo.mark_orphaned_started_as_failed() == 1
    assert await repo.mark_orphaned_started_as_failed() == 0


async def test_finished_and_failed_docs_untouched(repo):
    stale = {"started_at": _ago(600), "heartbeat_at": _ago(600)}
    await _insert(repo, "run-finished", "finished", **stale)
    await _insert(repo, "run-failed", "failed", **stale)

    assert await repo.mark_orphaned_started_as_failed() == 0
    assert await _status(repo, "run-finished") == "finished"
    assert await _status(repo, "run-failed") == "failed"
