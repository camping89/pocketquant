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
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import Settings

if TYPE_CHECKING:
    from pocketquant.core.infra.persistence.repositories.job_history_repository import (
        JobHistoryRepository,
    )

logger = get_logger(__name__)


# Only one scheduler may run at a time: APScheduler 3 on a shared job store runs jobs
# twice or skips them. Jobs are text references ("module.path:func") to module-level
# coroutines, never closures, so they serialize into Mongo.
class JobScheduler:
    def __init__(self, history_repo: JobHistoryRepository | None = None) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        # The listeners persist missed/skipped/failed events through history_repo.
        # Wrapper-path writes use UUID keys; listener-path writes use
        # (job_id, scheduled_run_time) idempotency keys — distinct namespaces.
        self._history_repo = history_repo
        self._loop: asyncio.AbstractEventLoop | None = None

    def initialize(self, settings: Settings) -> None:
        # Only one scheduler runs at a time; the Mongo store only keeps jobs across restarts.
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

    # Persists missed and max-instances skips so they show up in /runs.
    def _on_skip(self, event: Any) -> None:
        status = "skipped_max_instances" if event.code == EVENT_JOB_MAX_INSTANCES else "missed"
        # A max-instances event is a submission event: it carries a list of run times.
        if event.code == EVENT_JOB_MAX_INSTANCES:
            run_time = event.scheduled_run_times[-1]
        else:
            run_time = event.scheduled_run_time
        self._dispatch_skip(event.job_id, run_time, status, None)

    # Catches errors raised before the job wrapper records anything. CancelledError has an
    # empty str(), so the type name is always emitted.
    def _on_error(self, event: Any) -> None:
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
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            logger.warning("scheduler.listener_dispatch_failed", exc_info=True)
            return

        def _log_failure(done: Any) -> None:
            if not done.cancelled() and done.exception() is not None:
                logger.warning(
                    "scheduler.record_skip_failed",
                    job_id=job_id,
                    error=type(done.exception()).__name__,
                )

        future.add_done_callback(_log_failure)

    def pause(self) -> None:
        if self._scheduler is not None:
            self._scheduler.pause()

    def shutdown(self, wait: bool = True) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=wait)
            self._scheduler = None
            logger.info("scheduler.stopped")

    # second offsets bar-aligned jobs past provider publish lag. A larger misfire_grace_time
    # keeps a restart past the global 300s window from dropping a heavy daily run.
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
        if self._scheduler is None:
            raise RuntimeError("Scheduler not initialized.")

        # APScheduler applies the scheduler's declared timezone only when add_job
        # builds the trigger itself from a string alias. A pre-built trigger with no
        # timezone= falls back to tzlocal and pickles the host zone into the Mongo
        # jobstore, so the same job fires at different instants per host.
        if cron_expression:
            parts = cron_expression.split()
            trigger = CronTrigger(
                minute=parts[0] if len(parts) > 0 else None,
                hour=parts[1] if len(parts) > 1 else None,
                day=parts[2] if len(parts) > 2 else None,
                month=parts[3] if len(parts) > 3 else None,
                day_of_week=parts[4] if len(parts) > 4 else None,
                second=second,
                timezone=UTC,
            )
        else:
            trigger = CronTrigger(
                hour=hour,
                minute=minute,
                second=second,
                day_of_week=day_of_week,
                timezone=UTC,
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

    # replace_existing so duplicate job_ids (concurrent run-all calls) replace safely.
    def add_one_off_job(
        self,
        func: Callable | str,
        *,
        job_id: str,
        run_at: datetime | None = None,
        **kwargs: Any,
    ) -> str:
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

    # get_jobs drops the trigger for the HTTP DTOs; startup invariant checks need it.
    def get_raw_jobs(self) -> list[Any]:
        if self._scheduler is None:
            return []
        return list(self._scheduler.get_jobs())
