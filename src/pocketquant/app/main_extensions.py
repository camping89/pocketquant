"""Helpers for main.py: middleware, routes, health, and startup utilities.

The app process is the single backend entrypoint — it runs the full trading
runtime (scheduler, WS feed, reconcile loop, backtest worker) AND serves all
HTTP feature routes plus the SPA.
"""

import asyncio
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from dishka import AsyncContainer
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pocketquant.app.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.app.market_data.app_services.ws_subscription_manager import WsSubscriptionManager
from pocketquant.core.common.exceptions import register_exception_handlers
from pocketquant.core.common.health import HealthCoordinator
from pocketquant.core.common.idempotency import IdempotencyMiddleware
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.rate_limit import RateLimitMiddleware
from pocketquant.core.common.tracing import CorrelationIDMiddleware, RequestLoggingMiddleware
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.interfaces import IRealtimeQuoteProvider
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
from pocketquant.core.infra.scheduling.scheduler import JobScheduler
from pocketquant.engine.app_services.strategy_reconcile_service import (
    StrategyReconcileService,
)

logger = get_logger(__name__)

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
    start_background_jobs (so new runs aren't racing the reconcile sweep).
    """
    repo = await container.get(JobHistoryRepository)
    n = await repo.reconcile_orphan_running(max_age_seconds=600)
    if n:
        logger.info("orphan_jobs_recovered", marked_failed=n)


async def rehydrate_strategies_from_subscriptions(container: AsyncContainer) -> None:
    """Re-load one strategy instance per persisted subscription on startup.

    Strategy instances live in-process and disappear on every container
    restart, but their subscriptions are durable in MongoDB. Each subscription
    owns its own runtime instance keyed by ``sub.id`` so that subscribing the
    same template to multiple (symbol, interval) pairs results in independent
    instances. Subscriptions whose template no longer exists in the registry
    are skipped with a warning.
    """
    from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
    from pocketquant.core.domain.strategy.value_objects import StrategyConfig
    from pocketquant.engine.app_services.strategy_app_service import StrategyAppService

    sub_repo = await container.get(SubscriptionRepository)
    strategy_service = await container.get(StrategyAppService)

    subs = await sub_repo.list_all()
    if not subs:
        return

    loaded = 0
    for sub in subs:
        sub_id = str(sub.id)
        if strategy_service.get_strategy(sub_id) is not None:
            continue
        strategy_class = STRATEGY_REGISTRY.get(sub.strategy_code)
        if strategy_class is None:
            logger.warning(
                "rehydrate_skipped_unknown_template",
                sub_id=sub_id,
                strategy_code=sub.strategy_code,
            )
            continue
        await strategy_service.load_strategy(
            StrategyConfig(
                id=sub_id,
                name=sub.strategy_code,
                symbol=sub.symbol,
                interval=sub.interval.value,
            ),
            strategy_class=strategy_class,
        )
        loaded += 1

    if loaded:
        logger.info("strategies_rehydrated", count=loaded)


async def start_background_jobs(container: AsyncContainer) -> None:
    """Register background sync jobs with the scheduler.

    NOTE: the sync_jobs module-level container is wired at the top of lifespan()
    in main.py — before any `await` — to win the race against persisted
    MongoDBJobStore jobs that may dispatch during early Dishka resolves.
    """
    settings = await container.get(Settings)
    if not settings.enable_jobs:
        logger.info("background_jobs_disabled")
        return

    from pocketquant.engine.market_data.app_services.sync_jobs import register_sync_jobs

    await register_sync_jobs(
        container=container,
        job_scheduler=await container.get(JobScheduler),
    )
    logger.info("background_jobs_enabled")


async def start_quote_feed(container: AsyncContainer, app: FastAPI) -> None:
    """Start WS feed + subscription reconcile loop as background tasks.

    Stores task handles on app.state for lifespan cleanup:
      app.state.ws_task          — IRealtimeQuoteProvider.run_forever()
      app.state.subscription_task — WsSubscriptionManager.run()
    """
    quote_svc = await container.get(QuoteAppService)
    sub_mgr = await container.get(WsSubscriptionManager)

    await quote_svc.start()
    app.state.ws_task = quote_svc.ws_task  # task created inside start()

    app.state.subscription_task = asyncio.create_task(sub_mgr.run())
    logger.info("quote_feed.started")


async def stop_quote_feed(container: AsyncContainer, app: FastAPI) -> None:
    for attr in ("ws_task", "subscription_task"):
        task: asyncio.Task | None = getattr(app.state, attr, None)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                pass

    provider = await container.get(IRealtimeQuoteProvider)
    await provider.disconnect()
    logger.info("quote_feed.stopped")


async def start_reconcile_loop(container: AsyncContainer, app: FastAPI) -> None:
    """Start the declarative control-plane reconcile loop as a background task.

    Gated on ``enable_jobs`` — same flag as background jobs, so the test/CLI
    profile (``enable_jobs=False``) never spins a live loop. Must start AFTER
    ``rehydrate_strategies_from_subscriptions`` so instances exist; otherwise the
    first tick logs N missing_instance warnings before catching up next tick.
    """
    settings = await container.get(Settings)
    if not settings.enable_jobs:
        logger.info("reconcile_loop_disabled")
        return

    svc = await container.get(StrategyReconcileService)
    app.state.reconcile_task = asyncio.create_task(svc.run())
    logger.info("reconcile_loop.started")


async def stop_reconcile_loop(container: AsyncContainer, app: FastAPI) -> None:
    """Cancel the reconcile task. Must run BEFORE quote-feed stop + container.close
    so reconcile never issues start/stop against an engine that is shutting down."""
    task: asyncio.Task | None = getattr(app.state, "reconcile_task", None)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
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


def handle_startup_failure(error: Exception) -> None:
    """Display a rich error panel and re-raise so lifespan finally block runs.

    Raises the original exception so FastAPI's lifespan context manager propagates
    it as a startup error (process exits), but the finally block in lifespan()
    executes first — cancelling WS/subscription tasks and closing the DI container.
    Using os._exit() would bypass that cleanup; sys.exit() / re-raise does not.
    """
    from rich.console import Console
    from rich.panel import Panel

    console = Console(stderr=True)
    console.print(
        Panel(
            f"[bold red]{type(error).__name__}[/]: {error}",
            title="Startup Failed",
            border_style="red",
        )
    )
    console.print("\n[dim]Your code:[/]")
    console.print("  -> [cyan]pocketquant.app.main[/] in lifespan")
    console.print("  -> [cyan]pocketquant.core.infra.persistence.mongodb[/] in connect")
    raise error


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
    app.add_middleware(IdempotencyMiddleware)
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
    from pocketquant.app.routes.market_data_quotes import router as quote_router
    from pocketquant.app.routes.strategy import strategy_router, subscription_router
    from pocketquant.app.routes.tracked_symbols import router as tracked_symbols_router
    from pocketquant.app.routes.trading_orders_positions import trading_router

    @app.get("/health")
    @inject
    async def health_check(
        health_coordinator: FromDishka[HealthCoordinator],
    ) -> dict:
        result = await health_coordinator.check_all()
        result["version"] = settings.app_version
        result["environment"] = settings.environment
        return result

    api = APIRouter(prefix=settings.api_prefix, route_class=DishkaRoute)

    @api.get("/system/jobs")
    async def list_jobs(
        database: FromDishka[Database],
        history_repo: FromDishka[JobHistoryRepository],
    ) -> list[dict]:
        # Read the APScheduler Mongo store directly — no scheduler API coupling,
        # and the route works identically when enable_jobs=false.
        return await _list_jobs_from_mongo(database, history_repo)

    from pocketquant.app.routes.system_jobs import router as system_jobs_router

    api.include_router(market_data_router)
    api.include_router(tracked_symbols_router, prefix="/market-data")
    api.include_router(quote_router)
    api.include_router(system_jobs_router)
    api.include_router(strategy_router)
    api.include_router(subscription_router)
    api.include_router(trading_router)
    api.include_router(backtest_router)

    app.include_router(api)

    # StaticFiles + SPA fallback — after API routes so /api/* is never intercepted
    # repo root = 4 levels up from src/pocketquant/app/main_extensions.py
    web_dist = Path(__file__).resolve().parents[3] / "web" / "dist"
    if web_dist.is_dir():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="static-assets")

        # include_in_schema=False: static-file serving, not API surface — keeps
        # OpenAPI/route snapshots independent of whether web/dist was built.
        @app.get("/{path:path}", include_in_schema=False)
        async def spa_fallback(path: str) -> FileResponse:
            file = web_dist / path
            if file.is_file():
                return FileResponse(file)
            return FileResponse(web_dist / "index.html")

        logger.info("spa_mounted", path=str(web_dist))
    else:
        # Expected in prod (web ships in its own container); locally it means
        # `npm run build` hasn't produced web/dist yet.
        logger.info("spa_not_mounted", path=str(web_dist))
