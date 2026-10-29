"""Helpers for main.py: middleware, routes, health, and startup utilities.

The app process is the single backend entrypoint — it runs the full trading
runtime (scheduler, WS feed, reconcile loop, backtest tasks) AND serves all
HTTP feature routes. nginx serves the SPA.
"""

import asyncio
import os
import time
from collections import deque
from datetime import UTC, datetime
from functools import partial
from typing import Any
from zoneinfo import ZoneInfoNotFoundError

import tzlocal
from dishka import AsyncContainer
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pocketquant.app.middleware.admin_auth_middleware import verify_admin_token
from pocketquant.core.common.exceptions import register_exception_handlers
from pocketquant.core.common.health import HealthCoordinator
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.rate_limit import RateLimitMiddleware
from pocketquant.core.common.tracing import CorrelationIDMiddleware, RequestLoggingMiddleware
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.realtime_quote_provider_port import (
    IRealtimeQuoteProviderPort,
)
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.exness.exness_client import ExnessClient
from pocketquant.core.infra.market_data.provider_health_check import check_market_data_providers
from pocketquant.core.infra.persistence.health_checks import check_database, check_redis
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.core.infra.persistence.repositories.lease_repository import LeaseRepository
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.infra.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.core.infra.persistence.repositories.trade_repository import TradeRepository
from pocketquant.core.infra.scheduling.scheduler import JobScheduler
from pocketquant.engine.live.live_trade_collector import LiveTradeCollector
from pocketquant.engine.live.strategy_reconcile_app_service import (
    StrategyReconcileAppService,
)
from pocketquant.engine.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.engine.market_data.app_services.ws_subscription_app_service import (
    WsSubscriptionAppService,
)

logger = get_logger(__name__)


def assert_utc_runtime() -> None:
    """Refuse to start unless the process timezone is UTC.

    Bars, cron triggers and session calendars are all UTC instants by
    construction, not by convention. On a non-UTC process they look correct on
    the VPS and wrong everywhere else, so fail fast rather than persist skewed
    data. Logs one INFO line when the zone is correct.
    """
    tz_env = os.environ.get("TZ")
    prefix = f"Process timezone must be UTC, got TZ={tz_env!r} tzname={time.tzname!r}"

    if time.timezone != 0 or time.daylight:
        raise RuntimeError(f"{prefix}. Set TZ=UTC.")

    try:
        tz_name = str(tzlocal.get_localzone_name())
    except ZoneInfoNotFoundError as exc:
        # A TZ naming a zone the platform cannot resolve (e.g. a tzdata-legacy
        # alias such as Asia/Saigon) degrades to UTC in libc, so the check above
        # passes. Report it the way an operator expects instead of letting a bare
        # lookup error surface from inside zoneinfo.
        raise RuntimeError(f"{prefix} which names no resolvable zone. Set TZ=UTC.") from exc

    if tz_name not in {"UTC", "Etc/UTC"}:
        raise RuntimeError(f"{prefix} tzlocal={tz_name!r}. Set TZ=UTC.")

    logger.info("runtime.timezone", tz=tz_env, tzname=time.tzname, tzlocal=tz_name)


# All repository types that need MongoDB indexes on startup
_REPO_TYPES: list[type] = [
    OrderRepository,
    PositionRepository,
    BacktestRepository,
    BacktestOrderRepository,
    BacktestTradeRepository,
    BarRepository,
    SyncStatusRepository,
    SymbolRepository,
    JobHistoryRepository,
    SubscriptionRepository,
    TrackedSymbolRepository,
    TradeRepository,
    LeaseRepository,
]


async def ensure_all_indexes(container: AsyncContainer) -> None:
    """Ensure MongoDB indexes for all repository collections."""
    repos = [await container.get(rt) for rt in _REPO_TYPES]
    await asyncio.gather(*(repo.ensure_indexes() for repo in repos))
    logger.info("database_indexes_ensured")


async def recover_orphan_backtests(container: AsyncContainer) -> None:
    """Flip any run left ``started`` by a killed task to ``failed`` on startup.

    Single uvicorn worker → no legitimately in-flight run survives a restart, so
    every ``started`` doc is an orphan. Without this, FE would poll it forever.
    """
    repo = await container.get(BacktestRepository)
    n = await repo.mark_orphaned_started_as_failed()
    if n:
        logger.info("orphan_backtest_recovery", marked_failed=n)


async def recover_orphan_jobs(container: AsyncContainer) -> None:
    """Mark any job_history docs stuck at status='running' as 'failed' on startup.

    Orphan rows arise when a job's wrapper writes record_start() but the
    process is killed before record_finish() runs (e.g. mid-deploy
    CancelledError). Without this sweep, dashboards show forever-running jobs.
    Safe to call repeatedly — idempotent. Logs once if any docs were updated.

    Must run AFTER ensure_all_indexes (proves DB connectivity) and BEFORE
    start_jobs (so new runs aren't racing the reconcile sweep).
    """
    repo = await container.get(JobHistoryRepository)
    n = await repo.reconcile_orphan_running(max_age_seconds=600)
    if n:
        logger.info("orphan_jobs_recovered", marked_failed=n)


async def bootstrap_live_instances(container: AsyncContainer) -> None:
    """Load one strategy instance per persisted subscription on startup.

    Strategy instances live in-process and vanish on every container restart,
    but their subscriptions are durable in MongoDB. Delegates to
    ``StrategyReconcileAppService.bootstrap`` — the same load-per-subscription
    pass the reconcile loop runs each tick — so the boot path and the
    steady-state path can never drift. Runs in the trader role only.
    """
    svc = await container.get(StrategyReconcileAppService)
    await svc.bootstrap()


async def cancel_task(task: asyncio.Task | None) -> None:
    """Cancel a background task and wait up to 5 s for it to finish."""
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass


_LAG_SAMPLE_S = 0.5
_LAG_WARN_S = 0.25
_LAG_WINDOW_SAMPLES = 120  # 60 s of 0.5 s samples


async def _run_loop_lag_probe(app: FastAPI) -> None:
    loop = asyncio.get_running_loop()
    samples: deque[float] = deque(maxlen=_LAG_WINDOW_SAMPLES)
    while True:
        started = loop.time()
        await asyncio.sleep(_LAG_SAMPLE_S)
        lag = max(0.0, loop.time() - started - _LAG_SAMPLE_S)
        samples.append(lag)
        app.state.loop_lag_max_s = round(max(samples), 3)
        if lag > _LAG_WARN_S:
            logger.warning("event_loop.lag", lag_s=round(lag, 3))


def start_loop_lag_probe(app: FastAPI) -> None:
    """Sample loop lag every 0.5 s; ``/health`` reports the 60 s maximum."""
    app.state.loop_lag_max_s = 0.0
    app.state.loop_lag_task = asyncio.create_task(_run_loop_lag_probe(app))


async def stop_loop_lag_probe(app: FastAPI) -> None:
    await cancel_task(getattr(app.state, "loop_lag_task", None))


async def start_quote_feed(container: AsyncContainer, app: FastAPI) -> None:
    """Start WS feed + subscription reconcile loop as background tasks.

    Stores task handles on app.state for lifespan cleanup:
      app.state.ws_task          — IRealtimeQuoteProviderPort.run_forever()
      app.state.close_timer_task — BarAppService.run_close_timer()
      app.state.subscription_task — WsSubscriptionAppService.run()
    """
    quote_svc = await container.get(QuoteAppService)
    sub_mgr = await container.get(WsSubscriptionAppService)

    await quote_svc.start()
    app.state.ws_task = quote_svc.ws_task  # task created inside start()
    app.state.close_timer_task = quote_svc.close_timer_task

    app.state.subscription_task = asyncio.create_task(sub_mgr.run())
    logger.info("quote_feed.started")


async def stop_quote_feed(container: AsyncContainer, app: FastAPI) -> None:
    await cancel_task(getattr(app.state, "close_timer_task", None))
    await cancel_task(getattr(app.state, "ws_task", None))
    await cancel_task(getattr(app.state, "subscription_task", None))

    provider = await container.get(IRealtimeQuoteProviderPort)
    await provider.disconnect()
    logger.info("quote_feed.stopped")


async def start_jobs(container: AsyncContainer, app: FastAPI) -> None:
    """Register the sync jobs, subscribe the live trade collector, start reconcile.

    All three run only in the worker role, so the test/CLI profile
    (``APP_ROLES=api``) runs none of them. The collector subscribes before the
    reconcile loop starts strategies, so no trade closure is published before its
    handler exists. Call it after ``bootstrap_live_instances``, so the loop's first
    tick finds every instance.

    The sync_jobs module-level container is wired at the top of lifespan() in
    main.py, before any ``await``, to win the race against persisted
    MongoDBJobStore jobs that may dispatch during early Dishka resolves.
    """
    settings = await container.get(Settings)
    if "worker" not in settings.roles:
        logger.info("background_jobs_disabled")
        return

    from pocketquant.engine.market_data.app_services.sync_jobs import register_sync_jobs

    await register_sync_jobs(
        container=container,
        job_scheduler=await container.get(JobScheduler),
    )
    collector = await container.get(LiveTradeCollector)
    await collector.start()
    svc = await container.get(StrategyReconcileAppService)
    app.state.reconcile_task = asyncio.create_task(svc.run())
    logger.info("background_jobs_enabled")


async def stop_reconcile_loop(app: FastAPI) -> None:
    """Cancel the reconcile task. Must run BEFORE quote-feed stop + container.close
    so reconcile never issues start/stop against an engine that is shutting down."""
    await cancel_task(getattr(app.state, "reconcile_task", None))
    logger.info("reconcile_loop.stopped")


def init_backtest_tasks(app: FastAPI) -> None:
    """Hold strong refs to in-flight ``/backtest/run`` tasks.

    asyncio only weak-references tasks, so without this set a run could be GC'd
    mid-flight. The route adds each task and discards it on completion.
    """
    app.state.backtest_tasks = set()


async def drain_backtest_tasks(app: FastAPI, timeout: float = 10.0) -> None:
    """Let in-flight backtests finish persisting before container.close().

    Drain (await) rather than cancel: cancelling mid-write risks a half-persisted
    run, and ``CancelledError`` is a ``BaseException`` the engine's ``except
    Exception`` would miss. Runs still ``started`` past the timeout are left for
    the next boot's orphan sweep to flip to ``failed``.
    """
    tasks: set[asyncio.Task] = getattr(app.state, "backtest_tasks", set())
    pending = {t for t in tasks if not t.done()}
    if not pending:
        return
    logger.info("backtest_tasks.draining", count=len(pending))
    _, still_pending = await asyncio.wait(pending, timeout=timeout)
    if still_pending:
        logger.warning("backtest_tasks.drain_timeout", abandoned=len(still_pending))


async def register_health_checks(container: AsyncContainer, app: FastAPI) -> None:
    hc = await container.get(HealthCoordinator)
    hc.register("database", partial(check_database, app.state.database))
    hc.register("redis", partial(check_redis, app.state.cache))

    exness_client = await container.get(ExnessClient)
    credentialed = {"exness"} if exness_client.is_configured else set()
    hc.register(
        "market_data_providers",
        partial(
            check_market_data_providers,
            {
                "binance": lambda: True,
                "exness": lambda: exness_client.is_configured,
            },
            credentialed,
            await container.get(TradingCalendarFactory),
            await container.get(TrackedSymbolRepository),
        ),
    )


def configure_middleware(app: FastAPI, settings) -> None:
    from fastapi.exceptions import RequestValidationError

    register_exception_handlers(app, validation_error_cls=RequestValidationError)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.environment == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, capacity=200, refill_rate=20.0)
    app.add_middleware(CorrelationIDMiddleware)


async def _list_jobs_from_mongo(
    database: Database, history_repo: JobHistoryRepository
) -> list[dict[str, Any]]:
    """Read apscheduler_jobs + job_history directly from Mongo.

    apscheduler_jobs stores serialised APScheduler job docs. We read raw Mongo
    docs and project only the stable fields (id, next_run_time). The func_ref
    is stored inside the pickled payload — we skip deserialisation and expose
    only the last-run enrichment from job_history instead.
    """
    coll = database.database["apscheduler_jobs"]
    raw_jobs = await coll.find({}, {"_id": 1, "next_run_time": 1}).to_list(length=200)

    job_ids = [doc["_id"] for doc in raw_jobs]
    last_runs: dict[str, dict[str, Any]] = {}
    if job_ids:
        try:
            last_runs = await history_repo.get_latest_by_job_ids(job_ids)
        except Exception:
            logger.warning("system_jobs.last_runs_failed", exc_info=True)

    result = []
    for doc in raw_jobs:
        job_id = doc["_id"]
        # MongoDBJobStore stores next_run_time as a UTC float timestamp
        # (datetime_to_utc_timestamp), None when the job is paused.
        next_run = doc.get("next_run_time")
        entry: dict[str, Any] = {
            "id": job_id,
            "next_run": (
                datetime.fromtimestamp(next_run, tz=UTC).isoformat()
                if next_run is not None
                else None
            ),
            "last_run": last_runs.get(job_id),
        }
        result.append(entry)
    return result


def register_routes(app: FastAPI, settings) -> None:
    from pocketquant.app.routes.backtest import backtest_router
    from pocketquant.app.routes.market_data import router as market_data_router
    from pocketquant.app.routes.market_data import tracked_symbols_router
    from pocketquant.app.routes.market_data_quotes import router as quote_router
    from pocketquant.app.routes.strategy import strategy_router, subscription_router

    @app.get("/health")
    @inject
    async def health_check(
        health_coordinator: FromDishka[HealthCoordinator],
    ) -> dict:
        result = await health_coordinator.check_all()
        result["version"] = settings.app_version
        result["environment"] = settings.environment
        result["event_loop_lag_max_s"] = getattr(app.state, "loop_lag_max_s", 0.0)
        return result

    api = APIRouter(
        prefix=settings.api_prefix,
        route_class=DishkaRoute,
        dependencies=[Depends(verify_admin_token)],
    )

    @api.get("/system/jobs")
    async def list_jobs(
        database: FromDishka[Database],
        history_repo: FromDishka[JobHistoryRepository],
    ) -> list[dict]:
        # Read the APScheduler Mongo store directly — no scheduler API coupling,
        # and the route works in every role.
        return await _list_jobs_from_mongo(database, history_repo)

    from pocketquant.app.routes.safeguards import router as safeguards_router
    from pocketquant.app.routes.system_jobs import router as system_jobs_router

    api.include_router(market_data_router)
    api.include_router(tracked_symbols_router, prefix="/market-data")
    api.include_router(quote_router)
    api.include_router(system_jobs_router)
    api.include_router(safeguards_router)
    api.include_router(strategy_router)
    api.include_router(subscription_router)
    api.include_router(backtest_router)

    app.include_router(api)
