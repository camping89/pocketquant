"""Unit tests for JobScheduler._on_skip: dropped runs become job_history rows."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import structlog
from apscheduler.events import (
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
    JobSubmissionEvent,
)

from pocketquant.core.infra.scheduling import scheduler as scheduler_module
from pocketquant.core.infra.scheduling.scheduler import JobScheduler

t1 = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
t2 = t1 + timedelta(minutes=1)


class _Repo:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def record_skip(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class _FailingRepo:
    async def record_skip(self, **kwargs: Any) -> None:
        raise RuntimeError("boom")


async def _fire(repo: Any, event: Any) -> None:
    scheduler = JobScheduler(history_repo=repo)
    scheduler._loop = asyncio.get_running_loop()
    scheduler._on_skip(event)
    await asyncio.sleep(0.05)


async def test_max_instances_event_records_the_latest_run_time() -> None:
    repo = _Repo()
    await _fire(repo, JobSubmissionEvent(EVENT_JOB_MAX_INSTANCES, "sync_1m", "default", [t1, t2]))
    assert repo.calls == [
        {
            "job_id": "sync_1m",
            "scheduled_run_time": t2,
            "status": "skipped_max_instances",
            "error": None,
        }
    ]


async def test_missed_event_records_its_run_time() -> None:
    repo = _Repo()
    await _fire(repo, JobExecutionEvent(EVENT_JOB_MISSED, "sync_1m", "default", t1))
    assert repo.calls == [
        {"job_id": "sync_1m", "scheduled_run_time": t1, "status": "missed", "error": None}
    ]


async def test_failed_write_logs_one_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(scheduler_module, "logger", structlog.get_logger("test.scheduler"))
    event = JobSubmissionEvent(EVENT_JOB_MAX_INSTANCES, "sync_1m", "default", [t1, t2])
    with structlog.testing.capture_logs() as logs:
        await _fire(_FailingRepo(), event)
    failures = [entry for entry in logs if entry["event"] == "scheduler.record_skip_failed"]
    assert len(failures) == 1
    assert failures[0]["job_id"] == "sync_1m"
    assert failures[0]["error"] == "RuntimeError"
