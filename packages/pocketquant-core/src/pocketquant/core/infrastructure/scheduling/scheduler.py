"""Background job scheduler — instance-based for DI container.

Uses APScheduler with MongoDBJobStore for distributed coordination across
multiple processes (e.g. local dev + VPS). Both instances share the same Mongo
collection; the first to update next_run_time wins each tick.

Jobs MUST be passed as text references (e.g. "module.path:func") so they can be
serialized into Mongo. Module-level coroutine functions only — no closures.
History recording lives inside each job function (see sync_jobs.py).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time import to_utc_iso
from pocketquant.core.config import Settings

if TYPE_CHECKING:
    from pocketquant.core.infrastructure.scheduling.job_history_repository import (
        JobHistoryRepository,
    )

logger = get_logger(__name__)


class JobScheduler:
    """APScheduler wrapper. Instance-based, managed by DI container."""

    def __init__(self, history_repo: JobHistoryRepository | None = None) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        # history_repo only used by get_jobs() to enrich /system/jobs response.
        # Job functions write history themselves (see sync_jobs._run_sync_job).
        self._history_repo = history_repo

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
            "misfire_grace_time": 60,
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
        logger.info("scheduler.started")

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
        day_of_week: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Register a cron job. `func` must be a text reference (see add_interval_job)."""
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
            )
        else:
            trigger = CronTrigger(
                hour=hour,
                minute=minute,
                day_of_week=day_of_week,
            )

        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            kwargs=kwargs,
        )

        logger.info(
            "scheduler.registered_cron_job",
            job_id=job_id,
            cron_hour=hour,
            cron_minute=minute,
            cron_day_of_week=day_of_week,
        )
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
