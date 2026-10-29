# IntervalTrigger without start_date anchors to scheduler-startup time, so a restart shifts
# the phase off the bar boundary (fires at :09 instead of :00 for 15m bars), and lag on
# bar-close events breaks strategy entries and exits.

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


# register_sync_jobs also resolves JobHistoryRepository for its catch-up sweep; its
# AsyncMock methods return None or empty so catch-up short-circuits.
class _FakeContainer:
    async def get(self, _type):
        repo = AsyncMock()
        # Catch-up sweep calls this; None means "no last success, skip catch-up".
        repo.get_last_successful_started_at = AsyncMock(return_value=None)
        return repo


# add_*_job only needs _scheduler set; start() would fail on asyncio.get_running_loop() in a
# sync test.
def _build_scheduler(settings: Settings) -> JobScheduler:
    sched = JobScheduler(history_repo=None)
    sched.initialize(settings)
    return sched


async def test_all_bar_aligned_jobs_use_cron_trigger(settings: Settings) -> None:
    scheduler = _build_scheduler(settings)
    await register_sync_jobs(_FakeContainer(), scheduler)  # type: ignore[arg-type]
    assert scheduler._scheduler is not None  # pyright: ignore[reportPrivateUsage]
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
    scheduler = _build_scheduler(settings)
    assert scheduler._scheduler is not None  # pyright: ignore[reportPrivateUsage]
    assert str(scheduler._scheduler.timezone) == "UTC", (  # pyright: ignore[reportPrivateUsage]
        "Scheduler must run in UTC so cron expressions match exchange bar boundaries."
    )
