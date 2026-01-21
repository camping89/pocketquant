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
    _scheduler: AsyncIOScheduler | None = None

    @classmethod
    def initialize(cls, settings: Settings) -> None:
        jobstores = {
            "default": MemoryJobStore(),
        }

        executors = {
            "default": AsyncIOExecutor(),
        }

        job_defaults = {
            "coalesce": True,
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
        if cls._scheduler is None:
            raise RuntimeError("Scheduler not initialized. Call initialize() first.")

        cls._scheduler.start()
        logger.info("job_scheduler_started")

    @classmethod
    def shutdown(cls, wait: bool = True) -> None:
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
        if cls._scheduler is None:
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
        if cls._scheduler is None:
            return False

        job = cls._scheduler.get_job(job_id)
        if job:
            job.modify(next_run_time=datetime.now())
            logger.info("job_triggered", job_id=job_id)
            return True

        return False
