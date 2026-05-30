"""Helpers for main.py: middleware, routes, and startup utilities."""

import asyncio
from functools import partial
from pathlib import Path

from dishka import AsyncContainer
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pocketquant.api.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.api.market_data.app_services.ws_subscription_manager import WsSubscriptionManager
from pocketquant.api.market_data.handlers.quotes.router import router as quote_router
from pocketquant.api.market_data.handlers.router import router as market_data_router
from pocketquant.api.market_data.handlers.tracked_symbols import router as tracked_symbols_router
from pocketquant.api.system_jobs.route import router as system_jobs_router
from pocketquant.backtest.handlers import backtest_router
from pocketquant.backtest.persistence.backtest_order_repository import BacktestOrderRepository
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.backtest.persistence.backtest_trade_repository import BacktestTradeRepository
from pocketquant.backtest.persistence.optimization_repository import (
    OptimizationRepository,
)
from pocketquant.core.common.exceptions import register_exception_handlers
from pocketquant.core.common.health import HealthCoordinator
from pocketquant.core.common.health.checks import check_database, check_redis
from pocketquant.core.common.idempotency import IdempotencyMiddleware
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.rate_limit import RateLimitMiddleware
from pocketquant.core.common.tracing import CorrelationIDMiddleware, RequestLoggingMiddleware
from pocketquant.core.config import Settings
from pocketquant.core.infrastructure.realtime_quote_provider import IRealtimeQuoteProvider
from pocketquant.core.infrastructure.scheduling.job_history_repository import JobHistoryRepository
from pocketquant.core.infrastructure.scheduling.scheduler import JobScheduler
from pocketquant.core.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.persistence.repositories.sync_status_repository import SyncStatusRepository
from pocketquant.core.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.trading.handlers.strategy import strategy_router, subscription_router
from pocketquant.trading.handlers.trading import trading_router
from pocketquant.trading.persistence.order_repository import OrderRepository
from pocketquant.trading.persistence.position_repository import PositionRepository
from pocketquant.trading.persistence.subscription_repository import (
    SubscriptionRepository,
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
    OptimizationRepository,
    JobHistoryRepository,
    SubscriptionRepository,
    TrackedSymbolRepository,
]


async def ensure_all_indexes(container: AsyncContainer) -> None:
    """Ensure MongoDB indexes for all repository collections."""
    repos = [await container.get(rt) for rt in _REPO_TYPES]
    await asyncio.gather(*(repo.ensure_indexes() for repo in repos))
    logger.info("database_indexes_ensured")


# Reverse migration (for rollback):
#     db.subscriptions.updateMany({}, {$rename: {strategy_code: "strategy_id"}})
#     db.subscriptions.renameCollection("strategy_subscriptions")
#     db.orders.updateMany({}, {$rename: {subscription_id: "strategy_id"}})
#     db.positions.updateMany({}, {$rename: {subscription_id: "strategy_id"}})
#     db.backtest_runs.updateMany({}, {$rename: {strategy_code: "strategy_id"}})
#     db.backtest_orders.updateMany({}, {$rename: {strategy_code: "strategy_id"}})
#     db.backtest_trades.updateMany({}, {$rename: {strategy_code: "strategy_id"}})
#     db.backtest_optimization_runs.updateMany({}, {$rename: {strategy_code: "strategy_id"}})
#
# Field rename matrix:
#     strategy_subscriptions → subscriptions:    strategy_id → strategy_code
#     orders:                                    strategy_id → subscription_id
#     positions:                                 strategy_id → subscription_id
#     backtest_runs:                             strategy_id → strategy_code
#     backtest_orders:                           strategy_id → strategy_code
#     backtest_trades:                           strategy_id → strategy_code
#     backtest_optimization_runs:                strategy_id → strategy_code


_LEGACY_INDEX_NAMES: dict[str, list[str]] = {
    "subscriptions": ["ix_strategy_subscriptions_strategy_id"],
    "orders": ["ix_orders_strategy_id"],
    "positions": ["ix_positions_strategy_id"],
    "backtest_runs": [
        "ix_backtests_strategy_id",
        "ix_backtests_strategy_started",
        "ix_backtests_strategy_sharpe",
        "ix_backtests_strategy_sortino",
        "ix_backtests_strategy_winrate",
    ],
    "backtest_orders": ["ix_btorders_strategy_status"],
    "backtest_trades": ["ix_bttrades_strategy_direction"],
    "backtest_optimization_runs": ["ix_optimizations_strategy_id"],
}

_FIELD_RENAME_MATRIX: list[tuple[str, str]] = [
    ("subscriptions", "strategy_code"),
    ("orders", "subscription_id"),
    ("positions", "subscription_id"),
    ("backtest_runs", "strategy_code"),
    ("backtest_orders", "strategy_code"),
    ("backtest_trades", "strategy_code"),
    ("backtest_optimization_runs", "strategy_code"),
]


async def _rename_collection_if_needed(db, old: str, new: str) -> bool:
    """Rename ``old`` collection to ``new`` if migration is pending. Idempotent.

    Returns True if a rename happened, False if already migrated.
    Raises RuntimeError if both collections exist (manual intervention required).
    """
    existing = await db.database.list_collection_names()
    old_exists = old in existing
    new_exists = new in existing

    if old_exists and new_exists:
        raise RuntimeError(
            f"Both '{old}' and '{new}' collections exist — "
            "manual cleanup required before migration can proceed."
        )
    if old_exists and not new_exists:
        await db.database[old].rename(new)
        logger.info("mongo_migration.collection_renamed", old=old, new=new)
        return True
    logger.info("mongo_migration.skipped", collection=old, reason="already_migrated")
    return False


async def _rename_field_if_needed(db, collection: str, old_field: str, new_field: str) -> int:
    """`$rename` ``old_field`` → ``new_field`` on docs that still have the legacy key.

    Returns the count of modified docs (0 if migration already ran on this collection).
    """
    coll = db.database[collection]
    pending = await coll.count_documents({old_field: {"$exists": True}})
    if pending == 0:
        logger.info(
            "mongo_migration.skipped",
            collection=collection,
            field=old_field,
            reason="already_migrated",
        )
        return 0
    result = await coll.update_many(
        {old_field: {"$exists": True}},
        {"$rename": {old_field: new_field}},
    )
    logger.info(
        "mongo_migration.renamed",
        collection=collection,
        old_field=old_field,
        new_field=new_field,
        modified_count=result.modified_count,
    )
    return result.modified_count


async def _drop_legacy_indexes(db, collection: str, index_names: list[str]) -> None:
    """Drop legacy named indexes; tolerate IndexNotFound for idempotency."""
    coll = db.database[collection]
    for name in index_names:
        try:
            await coll.drop_index(name)
            logger.info("mongo_migration.dropped_index", collection=collection, index=name)
        except Exception as exc:
            # IndexNotFound (code 27) is benign — already dropped on a prior run.
            msg = str(exc)
            if "IndexNotFound" in msg or "index not found" in msg.lower() or "27" in msg:
                continue
            logger.warning(
                "mongo_migration.drop_index_failed",
                collection=collection,
                index=name,
                error=msg,
            )


async def migrate_strategy_id_fields(container: AsyncContainer) -> None:
    """Idempotent boot-time migration: rename ``strategy_id`` → ``strategy_code`` / ``subscription_id``.

    Runs BEFORE ``rehydrate_strategies_from_subscriptions`` so the rehydrate
    reads the new field name. Safe to call repeatedly — each step checks
    pending state before doing work.

    Steps:
      1. Rename collection ``strategy_subscriptions`` → ``subscriptions``.
      2. Per-collection ``$rename`` of the legacy ``strategy_id`` field.
      3. Drop legacy named indexes. ``ensure_all_indexes`` re-creates the new ones.
    """
    from pocketquant.core.persistence.mongodb import Database

    database = await container.get(Database)

    total_renamed = 0
    try:
        await _rename_collection_if_needed(
            database, old="strategy_subscriptions", new="subscriptions"
        )
        for collection, new_field in _FIELD_RENAME_MATRIX:
            renamed = await _rename_field_if_needed(
                database, collection, old_field="strategy_id", new_field=new_field
            )
            total_renamed += renamed
        for collection, names in _LEGACY_INDEX_NAMES.items():
            await _drop_legacy_indexes(database, collection, names)
    except Exception:
        logger.exception("mongo_migration.failed")
        raise

    logger.info("mongo_migration.completed", total_renamed=total_renamed)


async def recover_stale_backtests(container: AsyncContainer) -> None:
    """Mark any backtest docs stuck in 'running' as 'failed' on startup.

    Safe to call repeatedly — idempotent. Logs once if any docs were updated.
    """
    repo = await container.get(BacktestRepository)
    n = await repo.mark_stale_running_as_failed()
    if n:
        logger.info("stale_backtest_recovery", marked_failed=n)


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
    from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY
    from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
    from pocketquant.trading.app_services.strategy_app_service import StrategyAppService

    sub_repo = await container.get(SubscriptionRepository)
    strategy_service = await container.get(StrategyAppService)

    subs = await sub_repo.list_all()
    if not subs:
        return

    loaded = 0
    for sub in subs:
        if strategy_service.get_strategy(sub.id) is not None:
            continue
        strategy_class = STRATEGY_REGISTRY.get(sub.strategy_code)
        if strategy_class is None:
            logger.warning(
                "rehydrate_skipped_unknown_template",
                sub_id=sub.id,
                strategy_code=sub.strategy_code,
            )
            continue
        await strategy_service.load_strategy(
            StrategyConfig(
                id=sub.id,
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

    NOTE: sync_jobs and backtest_jobs module-level containers are wired at the
    top of lifespan() in main.py — before any `await` — to win the race against
    persisted MongoDBJobStore jobs that may dispatch during early Dishka resolves.
    """
    settings = await container.get(Settings)
    if not settings.enable_jobs:
        logger.info("background_jobs_disabled")
        return

    from pocketquant.api.market_data.app_services.sync_jobs import register_sync_jobs

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
    """Cancel WS + subscription tasks then disconnect the provider. 5s timeout each."""
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


async def register_health_checks(container: AsyncContainer, app: FastAPI) -> None:
    """Register health check functions with the coordinator."""
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
    console.print("  -> [cyan]pocketquant.api.main[/] in lifespan")
    console.print("  -> [cyan]pocketquant.core.persistence.mongodb[/] in connect")
    raise error


def configure_middleware(app: FastAPI, settings) -> None:
    """Attach all middleware layers and global exception handlers."""
    register_exception_handlers(app)

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


def register_routes(app: FastAPI, settings) -> None:
    """Register health/system endpoints and all feature routers."""

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
    async def list_jobs(job_scheduler: FromDishka[JobScheduler]) -> list[dict]:
        return await job_scheduler.get_jobs()

    api.include_router(market_data_router)
    api.include_router(tracked_symbols_router, prefix="/market-data")
    api.include_router(quote_router)
    api.include_router(system_jobs_router)
    api.include_router(strategy_router)
    api.include_router(subscription_router)
    api.include_router(trading_router)
    api.include_router(backtest_router)

    app.include_router(api)

    # After API routes — SPA fallback must not intercept /api/* paths
    web_dist = (
        Path(__file__).resolve().parent.parent.parent.parent.parent / "pocketquant-web" / "dist"
    )
    if web_dist.is_dir():
        from fastapi.responses import FileResponse

        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="static-assets")

        @app.get("/{path:path}")
        async def spa_fallback(path: str) -> FileResponse:
            """Serve index.html for all non-API routes (SPA fallback)."""
            file = web_dist / path
            if file.is_file():
                return FileResponse(file)
            return FileResponse(web_dist / "index.html")

        logger.info("spa_mounted", path=str(web_dist))
