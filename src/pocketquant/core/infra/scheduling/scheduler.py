"""Background job scheduler — instance-based for DI container.

Uses APScheduler with MongoDBJobStore for distributed coordination across
multiple processes (e.g. local dev + VPS). Both instances share the same Mongo
collection; the first to update next_run_time wins each tick.

Jobs MUST be passed as text references (e.g. "module.path:func") so they can be
serialized into Mongo. Module-level coroutine functions only — no closures.
History recording lives inside each job function (see sync_jobs.py).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
)
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time import to_utc_iso
from pocketquant.core.config import Settings

if TYPE_CHECKING:
    from pocketquant.core.infra.persistence.repositories.job_history_repository import (
        JobHistoryRepository,
    )

logger = get_logger(__name__)


class JobScheduler:
    """APScheduler wrapper. Instance-based, managed by DI container."""

    def __init__(self, history_repo: JobHistoryRepository | None = None) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        # history_repo used by get_jobs() to enrich /system/jobs response AND by
        # listeners to persist missed/skipped/failed events. Wrapper-path writes
        # use UUID keys; listener-path writes use (job_id, scheduled_run_time)
        # idempotency keys — distinct namespaces, no collision.
        self._history_repo = history_repo
        self._loop: asyncio.AbstractEventLoop | None = None

    def initialize(self, settings: Settings) -> None:
        # MongoDBJobStore = distributed coordination across processes (VPS + local).
        # Each tick, scheduler instances race to update next_run_time in Mongo;
        # the loser's view becomes stale and skips. No extra lock layer needed.
        jobstores = {
            "default": MongoDBJobStore(
                database=settings.mongodb_database,
                collection="apscheduler_jobs",
                host=str(settings.mongodb_url),
            )
        }
        executors = {"default": AsyncIOExecutor()}
        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            # 5 min grace — restarts/GC pauses no longer drop ticks silently.
            "misfire_grace_time": 300,
        }

        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone="UTC",
        )
        logger.info("scheduler.initialized")

    def start(self) -> None:
        if self._scheduler is None:
            raise RuntimeError("Scheduler not initialized. Call initialize() first.")
        self._scheduler.start()
        # Capture running loop so listener callbacks (which fire in scheduler
        # thread) can schedule async writes thread-safely.
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        if self._history_repo is not None:
            self._scheduler.add_listener(self._on_skip, EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES)
            self._scheduler.add_listener(self._on_error, EVENT_JOB_ERROR)
        logger.info("scheduler.started")

    def _on_skip(self, event: Any) -> None:
        """APScheduler EVENT_JOB_MISSED / EVENT_JOB_MAX_INSTANCES handler.
        Persists a record so silent skips become visible in /runs."""
        status = "skipped_max_instances" if event.code == EVENT_JOB_MAX_INSTANCES else "missed"
        self._dispatch_skip(event.job_id, event.scheduled_run_time, status, None)

    def _on_error(self, event: Any) -> None:
        """APScheduler EVENT_JOB_ERROR handler — captures exceptions raised
        before the wrapper records anything (rare but possible on startup).

        Emits ``<ExcType>: <msg>`` or ``<ExcType>(no message)`` instead of bare
        ``""``. Deploy-cancellations (CancelledError) carry an empty str(); the
        old bare path masked them as "unknown failure".
        """
        exc = event.exception
        if exc is None:
            err = "unknown_error_no_exception"
        else:
            msg = str(exc)
            err = f"{type(exc).__name__}: {msg}" if msg else f"{type(exc).__name__}(no message)"
        self._dispatch_skip(event.job_id, event.scheduled_run_time, "failed", err)

    def _dispatch_skip(
        self,
        job_id: str,
        scheduled_run_time: datetime | None,
        status: str,
        error: str | None,
    ) -> None:
        if self._history_repo is None or self._loop is None or scheduled_run_time is None:
            return
        coro = self._history_repo.record_skip(
            job_id=job_id,
            scheduled_run_time=scheduled_run_time,
            status=status,
            error=error,
        )
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            logger.warning("scheduler.listener_dispatch_failed", exc_info=True)

    def shutdown(self, wait: bool = True) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=wait)
            self._scheduler = None
            logger.info("scheduler.stopped")

    def add_interval_job(
        self,
        func: Callable | str,
        *,
        job_id: str,
        seconds: int | None = None,
        minutes: int | None = None,
        hours: int | None = None,
        start_date: datetime | None = None,
        **kwargs: Any,
    ) -> str:
        """Register an interval job. `func` must be a text reference (e.g. "pkg.mod:func")
        when using a persistent jobstore — closures cannot be serialized."""
        if self._scheduler is None:
            raise RuntimeError("Scheduler not initialized.")

        trigger_kwargs: dict[str, Any] = {}
        if seconds is not None:
            trigger_kwargs["seconds"] = seconds
        if minutes is not None:
            trigger_kwargs["minutes"] = minutes
        if hours is not None:
            trigger_kwargs["hours"] = hours
        if start_date is not None:
            trigger_kwargs["start_date"] = start_date

        trigger = IntervalTrigger(**trigger_kwargs)

        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            kwargs=kwargs,
        )

        logger.info(
            "scheduler.registered_interval_job",
            job_id=job_id,
            interval_seconds=seconds,
            interval_minutes=minutes,
            interval_hours=hours,
        )
        return job_id

    def add_cron_job(
        self,
        func: Callable | str,
        *,
        job_id: str,
        cron_expression: str | None = None,
        hour: str | int | None = None,
        minute: str | int | None = None,
        second: str | int | None = None,
        day_of_week: str | None = None,
        misfire_grace_time: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Register a cron job. `func` must be a text reference (see add_interval_job).

        `second` defaults to 0 in APScheduler when omitted; pass an explicit value
        (e.g. ``second=2``) to offset bar-aligned jobs past provider publish lag.

        `misfire_grace_time` (seconds) overrides the global default for this job.
        Pass a larger value (e.g. 3600) for heavy daily jobs so a restart spanning
        the global 300s window does not silently drop the run.
        """
        if self._scheduler is None:
            raise RuntimeError("Scheduler not initialized.")

        if cron_expression:
            parts = cron_expression.split()
            trigger = CronTrigger(
                minute=parts[0] if len(parts) > 0 else None,
                hour=parts[1] if len(parts) > 1 else None,
                day=parts[2] if len(parts) > 2 else None,
                month=parts[3] if len(parts) > 3 else None,
                day_of_week=parts[4] if len(parts) > 4 else None,
                second=second,
            )
        else:
            trigger = CronTrigger(
                hour=hour,
                minute=minute,
                second=second,
                day_of_week=day_of_week,
            )

        # Only forward misfire_grace_time when explicitly set so APScheduler falls
        # back to job_defaults["misfire_grace_time"] otherwise (backwards compat).
        job_kwargs: dict[str, Any] = {
            "id": job_id,
            "replace_existing": True,
            "kwargs": kwargs,
        }
        if misfire_grace_time is not None:
            job_kwargs["misfire_grace_time"] = misfire_grace_time

        self._scheduler.add_job(func, trigger=trigger, **job_kwargs)

        logger.info(
            "scheduler.registered_cron_job",
            job_id=job_id,
            cron_hour=hour,
            cron_minute=minute,
            cron_second=second,
            cron_day_of_week=day_of_week,
            misfire_grace_time=misfire_grace_time,
        )
        return job_id

    def add_one_off_job(
        self,
        func: Callable | str,
        *,
        job_id: str,
        run_at: datetime | None = None,
        **kwargs: Any,
    ) -> str:
        """Schedule a one-off job using DateTrigger.

        Defaults to immediate execution (run_at=now). Uses replace_existing=True
        so duplicate job_ids (e.g. concurrent run-all calls) replace safely.
        `func` should be a text reference (e.g. "pkg.mod:func") for Mongo persistence.
        """
        if self._scheduler is None:
            raise RuntimeError("Scheduler not initialized.")

        trigger = DateTrigger(run_date=run_at or datetime.now(UTC))
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            kwargs=kwargs,
        )
        logger.info("scheduler.registered_one_off_job", job_id=job_id, run_at=run_at)
        return job_id

    def remove_job(self, job_id: str) -> bool:
        if self._scheduler is None:
            return False

        try:
            self._scheduler.remove_job(job_id)
            logger.info("scheduler.removed_job", job_id=job_id)
            return True
        except JobLookupError:
            logger.warning("scheduler.job_not_found", job_id=job_id)
            return False

    async def get_jobs(self) -> list[dict[str, Any]]:
        if self._scheduler is None:
            return []

        raw_jobs = self._scheduler.get_jobs()
        job_ids = [j.id for j in raw_jobs]

        last_runs: dict[str, dict[str, Any]] = {}
        if self._history_repo and job_ids:
            try:
                last_runs = await self._history_repo.get_latest_by_job_ids(job_ids)
            except Exception:
                logger.warning("scheduler.get_last_runs_failed", exc_info=True)

        jobs = []
        for job in raw_jobs:
            entry: dict[str, Any] = {
                "id": job.id,
                "name": job.name,
                "next_run": to_utc_iso(job.next_run_time),
                "trigger": str(job.trigger),
                "last_run": last_runs.get(job.id),
            }
            jobs.append(entry)
        return jobs

    def run_job_now(self, job_id: str) -> bool:
        if self._scheduler is None:
            return False

        job = self._scheduler.get_job(job_id)
        if job:
            job.modify(next_run_time=datetime.now(UTC))
            logger.info("scheduler.triggered_job", job_id=job_id)
            return True

        return False
