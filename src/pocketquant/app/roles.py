from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from dishka import AsyncContainer
from fastapi import FastAPI

from pocketquant.app.main_extensions import (
    bootstrap_live_instances,
    cancel_task,
    recover_orphan_jobs,
    stop_reconcile_loop,
)
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time.simulation import get_current_time
from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.repositories.lease_repository import LeaseRepository
from pocketquant.core.infra.scheduling.scheduler import JobScheduler
from pocketquant.engine.live.live_trade_collector import LiveTradeCollector
from pocketquant.engine.live.strategy_reconcile_app_service import StrategyReconcileAppService
from pocketquant.engine.market_data.app_services.bar_app_service import BarAppService
from pocketquant.engine.market_data.app_services.sync_jobs import (
    register_sync_jobs,
    stop_running_jobs,
)
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

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


# state[name] is held only after on_acquired returned, so health and a waiting copy
# never see a holder that has not finished its takeover.
async def hold_lease(
    repo: LeaseRepository,
    name: str,
    owner: str,
    state: dict[str, str],
    on_acquired: Callable[[datetime], Awaitable[None]],
    on_lost: Callable[[], Awaitable[None]],
    on_renewed: Callable[[datetime], None],
) -> None:
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
    async def on_acquired(expires: datetime) -> None:
        scheduler = await container.get(JobScheduler)
        await recover_orphan_jobs(container)
        scheduler.initialize(await container.get(Settings))
        scheduler.start()
        await register_sync_jobs(container=container, job_scheduler=scheduler)

    async def on_lost() -> None:
        # The exit runs even when the stop fails: a lost role must never sit behind a healthy app.
        try:
            (await container.get(JobScheduler)).shutdown(wait=False)
        finally:
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
    task = getattr(app.state, "worker_lease_task", None)
    if task is None:
        return
    if app.state.lease_state.get("worker") != "held":
        await cancel_task(task)
        return
    scheduler = await container.get(JobScheduler)
    scheduler.pause()
    left = await stop_running_jobs(
        (started + timedelta(seconds=WORKER_STOP_S) - get_current_time()).total_seconds()
    )
    if left:
        logger.warning("worker.jobs_interrupted", count=left)
    # Renewal runs until here; stopped before the release so it cannot take the lease back.
    await cancel_task(task)
    scheduler.shutdown(wait=False)
    await (await container.get(LeaseRepository)).release("worker", owner)
    app.state.lease_state["worker"] = "released"
    logger.info("worker.lease_released", running=left)


async def start_trader_standby(container: AsyncContainer, started_at: float) -> None:
    engine = await container.get(StrategyAppService)
    engine.trading_until = None
    # Only the trader lease holder writes or deletes bar:current.
    (await container.get(BarAppService)).publishes_current = False
    await bootstrap_live_instances(container)
    logger.info(
        "trader.standby",
        warmup_s=round(time.monotonic() - started_at, 1),
        strategies=len(engine.loaded_strategy_ids()),
    )


def start_trader_lease(container: AsyncContainer, app: FastAPI, owner: str) -> None:
    waiting_since = datetime.now(UTC)

    async def run() -> None:
        repo = await container.get(LeaseRepository)
        engine = await container.get(StrategyAppService)
        bars = await container.get(BarAppService)

        async def take_over(expires: datetime) -> None:
            t0 = time.monotonic()
            doc = await repo.get("trader")
            released = doc.get("released_at") if doc else None
            # Empty when the previous holder lost the lease instead of releasing it.
            gap_ms = (
                round((datetime.now(UTC) - released).total_seconds() * 1000)
                if released and released >= waiting_since
                else None
            )
            logger.info("trader.takeover", handover_gap_ms=gap_ms)
            bars.publishes_current = True
            # Before take_over() connects the paper brokers, so no paper exit closes unrecorded.
            await (await container.get(LiveTradeCollector)).start()
            await engine.take_over()
            reconcile = await container.get(StrategyReconcileAppService)
            app.state.reconcile_task = asyncio.create_task(reconcile.run())
            engine.trading_until = expires - timedelta(seconds=ORDER_MARGIN_S)
            logger.info(
                "trader.takeover_complete", takeover_ms=round((time.monotonic() - t0) * 1000)
            )

        def on_renewed(expires: datetime) -> None:
            # A drained or lost trader is never re-armed.
            if engine.trading_until is not None:
                engine.trading_until = expires - timedelta(seconds=ORDER_MARGIN_S)

        async def on_lost() -> None:
            engine.trading_until = None
            engine.cancel_pending_signals()
            bars.publishes_current = False
            # The exit runs even when the stop fails: a lost role must never sit behind a
            # healthy app.
            try:
                await stop_reconcile_loop(app)
                # A send already under way gets the margin for its ACK.
                await engine.stop(ORDER_MARGIN_S)
            finally:
                os.kill(os.getpid(), signal.SIGTERM)

        await hold_lease(
            repo, "trader", owner, app.state.lease_state, take_over, on_lost, on_renewed
        )

    app.state.trader_lease_task = asyncio.create_task(run())


async def drain_trader(
    engine: StrategyAppService, bars: BarAppService, started: datetime
) -> tuple[int, datetime]:
    deadline = started + timedelta(seconds=DRAIN_DEADLINE_S)
    boundary = started.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for attempt in (1, 2):
        await _sleep(max(0.0, (boundary - get_current_time()).total_seconds()))
        window_end = min(boundary + timedelta(seconds=DRAIN_WINDOW_S), deadline)
        while get_current_time() < window_end:
            closed = bars.last_closed_boundary
            if closed is not None and closed >= boundary and engine.inflight_count() == 0:
                # Same step as the check: nothing new starts.
                engine.trading_until = None
                return 0, boundary
            await _sleep(0.2)
        if attempt == 1:
            logger.info(
                "trader.drain_retry",
                boundary=boundary.isoformat(),
                inflight=engine.inflight_count(),
            )
            boundary += timedelta(minutes=1)
    inflight = engine.inflight_count()
    engine.trading_until = None
    logger.error("trader.drain_timeout", boundary=boundary.isoformat(), inflight=inflight)
    return inflight, boundary


async def hand_over(container: AsyncContainer, app: FastAPI, owner: str, started: datetime) -> None:
    task = getattr(app.state, "trader_lease_task", None)
    if task is None:
        return
    if app.state.lease_state.get("trader") != "held":
        # Standby or lost: a lost lease skips the wait.
        await cancel_task(task)
        return
    engine = await container.get(StrategyAppService)
    bars = await container.get(BarAppService)
    inflight, boundary = await drain_trader(engine, bars, started)
    await stop_reconcile_loop(app)
    stop_by = started + timedelta(seconds=STOP_DEADLINE_S)
    await engine.stop(max(0.0, (stop_by - get_current_time()).total_seconds()))
    bars.publishes_current = False
    # Renewal ran until here; cancelled before the release so it cannot take the lease back.
    await cancel_task(task)
    await (await container.get(LeaseRepository)).release("trader", owner)
    app.state.lease_state["trader"] = "released"
    logger.info(
        "trader.lease_released",
        inflight=inflight,
        boundary=boundary.isoformat(),
        offset_s=round((get_current_time() - boundary).total_seconds(), 3),
    )
