"""Regression guard: every interval-mapped sync job MUST use UTC wall-clock cron.

Lag or gaps on bar-close events break strategy entries/exits. `IntervalTrigger`
without `start_date` anchors to scheduler-startup time, so restarts shift the
phase off the bar boundary (e.g. fires at :09 instead of :00 for 15m bars).
This test catches reintroduction of `IntervalTrigger` for any bar-aligned job.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from pocketquant.core.config import Settings
from pocketquant.core.infra.scheduling.scheduler import JobScheduler
from pocketquant.engine.market_data.app_services.sync_jobs import register_sync_jobs

# Jobs that ingest bars at fixed intervals — MUST be wall-clock-aligned.
# sync_1m runs per minute; cascades to higher tfs in-process.
# verify/backfill/integrity/repair remain bar-aligned cron jobs.
BAR_ALIGNED_JOB_IDS: set[str] = {
    "sync_1m",
    "sync_verify_cascade",
    "sync_backfill",
    "sync_integrity",
    "sync_repair",
}


class _FakeContainer:
    """Minimal stand-in for AsyncContainer.

    register_sync_jobs both stores the ref AND resolves JobHistoryRepository
    for its catch-up sweep — give it a no-op `.get(...)` that returns an
    AsyncMock whose own coroutine methods (e.g. find_last_success) return
    None / empty so the catch-up logic short-circuits.
    """

    async def get(self, _type):
        repo = AsyncMock()
        # Catch-up sweep calls this; None means "no last success, skip catch-up".
        repo.get_last_successful_started_at = AsyncMock(return_value=None)
        return repo


def _build_scheduler(settings: Settings) -> JobScheduler:
    """Initialize scheduler without start() — add_*_job only needs _scheduler!=None.

    Avoids `asyncio.get_running_loop()` failure in sync test context.
    """
    sched = JobScheduler(history_repo=None)
    sched.initialize(settings)
    return sched


async def test_all_bar_aligned_jobs_use_cron_trigger(settings: Settings) -> None:
    """No bar-aligned job may use IntervalTrigger — must be CronTrigger only."""
    scheduler = _build_scheduler(settings)
    await register_sync_jobs(_FakeContainer(), scheduler)  # type: ignore[arg-type]
    jobs = scheduler._scheduler.get_jobs()  # pyright: ignore[reportPrivateUsage]

    registered_ids = {j.id for j in jobs}
    missing = BAR_ALIGNED_JOB_IDS - registered_ids
    assert not missing, f"Expected jobs not registered: {missing}"

    for job in jobs:
        if job.id not in BAR_ALIGNED_JOB_IDS:
            continue
        assert isinstance(job.trigger, CronTrigger), (
            f"Job '{job.id}' uses {type(job.trigger).__name__} — must be CronTrigger "
            f"to keep phase aligned to UTC wall-clock across restarts."
        )
        assert not isinstance(job.trigger, IntervalTrigger), (
            f"Job '{job.id}' regressed to IntervalTrigger — would drift phase on restart."
        )


def test_scheduler_runs_in_utc(settings: Settings) -> None:
    """Cron expressions evaluate against scheduler timezone — must be UTC."""
    scheduler = _build_scheduler(settings)
    assert str(scheduler._scheduler.timezone) == "UTC", (  # pyright: ignore[reportPrivateUsage]
        "Scheduler must run in UTC so cron expressions match exchange bar boundaries."
    )
