"""Background job scheduler using APScheduler for scheduled tasks."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.common.logging import get_logger
from src.config import Settings

logger = get_logger(__name__)


class JobScheduler:
    """Centralized job scheduler for background tasks.

    Uses APScheduler for scheduled/recurring jobs.
    For one-off async background tasks, use asyncio.create_task() directly.
    """

    _scheduler: AsyncIOScheduler | None = None

    @classmethod
    def initialize(cls, settings: Settings) -> None:
        """Initialize the job scheduler.

        Args:
            settings: Application settings.
        """
        jobstores = {
            "default": MemoryJobStore(),
        }

        executors = {
            "default": AsyncIOExecutor(),
        }

        job_defaults = {
            "coalesce": True,  # Combine missed runs into one
            "max_instances": 3,
            "misfire_grace_time": 60,
        }

        cls._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone="UTC",
        )

        logger.info("job_scheduler_initialized")

    @classmethod
    def start(cls) -> None:
        """Start the scheduler."""
        if cls._scheduler is None:
            raise RuntimeError("Scheduler not initialized. Call initialize() first.")

        cls._scheduler.start()
        logger.info("job_scheduler_started")

    @classmethod
    def shutdown(cls, wait: bool = True) -> None:
        """Shutdown the scheduler.

        Args:
            wait: Whether to wait for running jobs to complete.
        """
        if cls._scheduler is not None:
            cls._scheduler.shutdown(wait=wait)
            cls._scheduler = None
            logger.info("job_scheduler_stopped")

    @classmethod
    def add_interval_job(
        cls,
        func: Callable,
        *,
        job_id: str,
        seconds: int | None = None,
        minutes: int | None = None,
        hours: int | None = None,
        start_date: datetime | None = None,
        **kwargs: Any,
    ) -> str:
        """Add a job that runs at fixed intervals.

        Args:
            func: The function to run (can be async).
            job_id: Unique identifier for this job.
            seconds: Interval in seconds.
            minutes: Interval in minutes.
            hours: Interval in hours.
            start_date: When to start running the job.
            **kwargs: Additional arguments passed to the function.

        Returns:
            The job ID.
        """
        if cls._scheduler is None:
            raise RuntimeError("Scheduler not initialized.")

        trigger = IntervalTrigger(
            seconds=seconds,
            minutes=minutes,
            hours=hours,
            start_date=start_date,
        )

        cls._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            kwargs=kwargs,
        )

        logger.info(
            "interval_job_added",
            job_id=job_id,
            seconds=seconds,
            minutes=minutes,
            hours=hours,
        )

        return job_id

    @classmethod
    def add_cron_job(
        cls,
        func: Callable,
        *,
        job_id: str,
        cron_expression: str | None = None,
        hour: str | int | None = None,
        minute: str | int | None = None,
        day_of_week: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Add a job that runs on a cron schedule.

        Args:
            func: The function to run (can be async).
            job_id: Unique identifier for this job.
            cron_expression: Full cron expression (e.g., "0 9 * * 1-5").
            hour: Hour to run (0-23).
            minute: Minute to run (0-59).
            day_of_week: Days to run (e.g., "mon-fri" or "0-4").
            **kwargs: Additional arguments passed to the function.

        Returns:
            The job ID.
        """
        if cls._scheduler is None:
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

        cls._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            kwargs=kwargs,
        )

        logger.info(
            "cron_job_added",
            job_id=job_id,
            hour=hour,
            minute=minute,
            day_of_week=day_of_week,
        )

        return job_id

    @classmethod
    def remove_job(cls, job_id: str) -> bool:
        """Remove a scheduled job.

        Args:
            job_id: The job ID to remove.

        Returns:
            True if job was removed, False if not found.
        """
        if cls._scheduler is None:
            return False

        try:
            cls._scheduler.remove_job(job_id)
            logger.info("job_removed", job_id=job_id)
            return True
        except Exception:
            logger.warning("job_not_found", job_id=job_id)
            return False

    @classmethod
    def get_jobs(cls) -> list[dict[str, Any]]:
        """Get all scheduled jobs.

        Returns:
            List of job information dictionaries.
        """
        if cls._scheduler is None:
            return []

        jobs = []
        for job in cls._scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
            )

        return jobs

    @classmethod
    def run_job_now(cls, job_id: str) -> bool:
        """Trigger a job to run immediately.

        Args:
            job_id: The job ID to run.

        Returns:
            True if job was triggered, False if not found.
        """
        if cls._scheduler is None:
            return False

        job = cls._scheduler.get_job(job_id)
        if job:
            job.modify(next_run_time=datetime.now())
            logger.info("job_triggered", job_id=job_id)
            return True

        return False
