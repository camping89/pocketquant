"""Cron triggers must carry an explicit UTC timezone, not the host's.

APScheduler applies the scheduler's declared timezone only when ``add_job``
builds the trigger from a string alias. A pre-built ``CronTrigger`` without an
explicit ``timezone=`` falls back to ``tzlocal``, so the same job fires at a
different instant on a VPS in UTC and a laptop in Asia/Ho_Chi_Minh — and the
host zone is pickled into the shared Mongo jobstore.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import MagicMock

from pocketquant.core.infra.scheduling.scheduler import JobScheduler


def _build_trigger(**cron_kwargs):
    """Register a cron job against a mocked APScheduler and return its trigger."""
    scheduler = JobScheduler()
    scheduler_mock = MagicMock()
    scheduler._scheduler = scheduler_mock
    scheduler.add_cron_job("module:func", job_id="test-job", **cron_kwargs)
    return scheduler_mock.add_job.call_args.kwargs["trigger"]


def test_cron_expression_trigger_is_utc() -> None:
    trigger = _build_trigger(cron_expression="0 3 * * *")

    assert str(trigger.timezone) == "UTC"


def test_hour_minute_trigger_is_utc() -> None:
    trigger = _build_trigger(hour=3, minute=0)

    assert str(trigger.timezone) == "UTC"


def test_next_run_time_identical_across_host_zones(
    host_timezone: Callable[..., None],
) -> None:
    reference = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    fire_times = []

    for zone in ("UTC", "Asia/Ho_Chi_Minh", "America/Chicago"):
        host_timezone(zone)
        trigger = _build_trigger(hour=3, minute=0)
        fire_times.append(trigger.get_next_fire_time(None, reference))

    assert fire_times[0] == fire_times[1] == fire_times[2]
