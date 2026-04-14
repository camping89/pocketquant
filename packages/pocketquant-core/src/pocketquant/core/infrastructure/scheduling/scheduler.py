"""Background job scheduler — instance-based for DI container."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import TYPE_CHECKING, Any

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.memory import MemoryJobStore
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
        self._history_repo = history_repo

    def initialize(self, settings: Settings) -> None:
        jobstores = {"default": MemoryJobStore()}
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

    def _wrap_with_history(self, job_id: str, func: Callable) -> Callable:
        """Wrap an async job func to record execution in history."""
        if self._history_repo is None:
            return func
        repo = self._history_repo

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> None:
            doc_id: str | None = None
            started_at = datetime.now(UTC)
            try:
                doc_id = await repo.record_start(job_id)
            except Exception:
                logger.warning("job_history.record_start_failed", job_id=job_id, exc_info=True)
            try:
                await func(*args, **kwargs)
                duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
                if doc_id:
                    try:
                        await repo.record_finish(doc_id, status="completed", duration_ms=duration_ms)
                    except Exception:
                        logger.warning("job_history.record_finish_failed", job_id=job_id, exc_info=True)
            except Exception as exc:
                duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
                if doc_id:
                    try:
                        await repo.record_finish(doc_id, status="failed", duration_ms=duration_ms, error=str(exc))
                    except Exception:
                        logger.warning("job_history.record_finish_failed", job_id=job_id, exc_info=True)
                raise

        return wrapper

    def add_interval_job(
        self,
        func: Callable,
        *,
        job_id: str,
        seconds: int | None = None,
        minutes: int | None = None,
        hours: int | None = None,
        start_date: datetime | None = None,
        **kwargs: Any,
    ) -> str:
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
        wrapped = self._wrap_with_history(job_id, func)

        self._scheduler.add_job(
            wrapped,
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
        func: Callable,
        *,
        job_id: str,
        cron_expression: str | None = None,
        hour: str | int | None = None,
        minute: str | int | None = None,
        day_of_week: str | None = None,
        **kwargs: Any,
    ) -> str:
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

        wrapped = self._wrap_with_history(job_id, func)

        self._scheduler.add_job(
            wrapped,
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
