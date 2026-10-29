"""Lease-holding roles.

The worker runs the scheduler and the trader sends orders, each only while it holds
its Mongo lease; a second copy waits in standby.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from dishka import AsyncContainer
from fastapi import FastAPI

from pocketquant.app.main_extensions import cancel_task, recover_orphan_jobs
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time.simulation import get_current_time
from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.repositories.lease_repository import LeaseRepository
from pocketquant.core.infra.scheduling.scheduler import JobScheduler
from pocketquant.engine.market_data.app_services.sync_jobs import (
    register_sync_jobs,
    wait_running_jobs,
)

logger = get_logger(__name__)

LEASE_TTL_S = 30.0
LEASE_RENEW_S = 10.0
LEASE_RETRY_S = 1.0
LEASE_POLL_S = 0.5
ORDER_MARGIN_S = 5.0
# These four count from shutdown start; trader grace 180 s and worker grace 120 s
# include up to 10 s of uvicorn graceful shutdown.
DRAIN_WINDOW_S = 30.0
DRAIN_DEADLINE_S = 150.0
STOP_DEADLINE_S = 160.0
WORKER_STOP_S = 90.0

_sleep = asyncio.sleep  # tests replace it


async def _try_acquire(repo: LeaseRepository, name: str, owner: str) -> datetime | None:
    try:
        return await repo.acquire(name, owner, LEASE_TTL_S)
    except Exception:
        logger.warning("lease.acquire_failed", name=name, owner=owner, exc_info=True)
        return None


async def hold_lease(
    repo: LeaseRepository,
    name: str,
    owner: str,
    state: dict[str, str],
    on_acquired: Callable[[datetime], Awaitable[None]],
    on_lost: Callable[[], Awaitable[None]],
    on_renewed: Callable[[datetime], None],
) -> None:
    """Wait for ``name``, take over, then renew until the lease is lost.

    ``state[name]`` is ``held`` only after ``on_acquired`` returned, so health and
    a waiting copy never see a holder that has not finished its takeover.
    """
    state[name] = "standby"
    expires = await _try_acquire(repo, name, owner)
    if expires is None:
        logger.info("lease.waiting", name=name, owner=owner)
        while expires is None:
            await _sleep(LEASE_POLL_S)
            expires = await _try_acquire(repo, name, owner)
    logger.info("lease.acquired", name=name, owner=owner)
    try:
        # A takeover that outlives the order margin would act on a lease another copy may take.
        await asyncio.wait_for(on_acquired(expires), LEASE_TTL_S - ORDER_MARGIN_S)
    except Exception:
        state[name] = "lost"
        logger.error("lease.takeover_failed", name=name, owner=owner, exc_info=True)
        with contextlib.suppress(Exception):
            await repo.release(name, owner)
        await on_lost()
        return
    state[name] = "held"
    delay = LEASE_RENEW_S
    while True:
        await _sleep(delay)
        try:
            renewed = await repo.acquire(name, owner, LEASE_TTL_S)
            taken = renewed is None
        except Exception:
            logger.warning("lease.renew_failed", name=name, exc_info=True)
            renewed, taken = None, False
        if renewed is not None:
            expires, delay = renewed, LEASE_RENEW_S
            on_renewed(expires)
            continue
        delay = LEASE_RETRY_S
        if taken or expires - datetime.now(UTC) <= timedelta(seconds=ORDER_MARGIN_S):
            state[name] = "lost"
            logger.error("lease.lost", name=name, owner=owner)
            await on_lost()
            return


def start_worker(container: AsyncContainer, app: FastAPI, owner: str) -> None:
    """Hold the worker lease; the scheduler starts only after it is taken."""

    async def on_acquired(expires: datetime) -> None:
        scheduler = await container.get(JobScheduler)
        await recover_orphan_jobs(container)
        scheduler.initialize(await container.get(Settings))
        scheduler.start()
        await register_sync_jobs(container=container, job_scheduler=scheduler)

    async def on_lost() -> None:
        (await container.get(JobScheduler)).shutdown(wait=False)
        os.kill(os.getpid(), signal.SIGTERM)

    async def run() -> None:
        repo = await container.get(LeaseRepository)
        await hold_lease(
            repo, "worker", owner, app.state.lease_state, on_acquired, on_lost, lambda _e: None
        )

    app.state.worker_lease_task = asyncio.create_task(run())


async def stop_worker(
    container: AsyncContainer, app: FastAPI, owner: str, started: datetime
) -> None:
    """Let running jobs finish (bounded), then release the worker lease."""
    task = getattr(app.state, "worker_lease_task", None)
    if task is None:
        return
    if app.state.lease_state.get("worker") != "held":
        await cancel_task(task)
        return
    scheduler = await container.get(JobScheduler)
    scheduler.pause()
    left = await wait_running_jobs(
        (started + timedelta(seconds=WORKER_STOP_S) - get_current_time()).total_seconds()
    )
    if left:
        logger.warning("worker.jobs_still_running", count=left)
    # Renewal runs until here; stopped before the release so it cannot take the lease back.
    await cancel_task(task)
    scheduler.shutdown(wait=False)
    await (await container.get(LeaseRepository)).release("worker", owner)
    app.state.lease_state["worker"] = "released"
    logger.info("worker.lease_released", running=left)
