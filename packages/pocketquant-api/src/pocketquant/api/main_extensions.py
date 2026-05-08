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
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
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
from pocketquant.trading.handlers.strategy import strategy_router
from pocketquant.trading.handlers.trading import trading_router
from pocketquant.trading.persistence.order_repository import OrderRepository
from pocketquant.trading.persistence.position_repository import PositionRepository
from pocketquant.trading.persistence.strategy_subscription_repository import (
    StrategySubscriptionRepository,
)

logger = get_logger(__name__)

# All repository types that need MongoDB indexes on startup
_REPO_TYPES: list[type] = [
    OrderRepository,
    PositionRepository,
    BacktestRepository,
    BarRepository,
    SyncStatusRepository,
    SymbolRepository,
    OptimizationRepository,
    JobHistoryRepository,
    StrategySubscriptionRepository,
    TrackedSymbolRepository,
]


# ---------------------------------------------------------------------------
# Lifespan helpers
# ---------------------------------------------------------------------------


async def ensure_all_indexes(container: AsyncContainer) -> None:
    """Ensure MongoDB indexes for all repository collections."""
    repos = [await container.get(rt) for rt in _REPO_TYPES]
    await asyncio.gather(*(repo.ensure_indexes() for repo in repos))
    logger.info("database_indexes_ensured")


async def recover_stale_backtests(container: AsyncContainer) -> None:
    """Mark any backtest docs stuck in 'running' as 'failed' on startup.

    Safe to call repeatedly — idempotent. Logs once if any docs were updated.
    """
    repo = await container.get(BacktestRepository)
    n = await repo.mark_stale_running_as_failed()
    if n:
        logger.info("stale_backtest_recovery", marked_failed=n)


async def start_background_jobs(container: AsyncContainer) -> None:
    """Register background sync jobs with the scheduler and wire backtest job container."""
    from pocketquant.trading.jobs.backtest_jobs import set_container as set_backtest_container

    # Always wire backtest jobs container so one-off jobs can resolve dependencies
    set_backtest_container(container)
    logger.info("backtest_jobs_container_wired")

    settings = await container.get(Settings)
    if not settings.enable_jobs:
        logger.info("background_jobs_disabled")
        return

    from pocketquant.api.market_data.app_services.sync_jobs import register_sync_jobs

    register_sync_jobs(
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


# ---------------------------------------------------------------------------
# App factory helpers
# ---------------------------------------------------------------------------


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
    api.include_router(trading_router)
    api.include_router(backtest_router)

    app.include_router(api)

    # Serve frontend SPA from pocketquant-web dist/ (must be after API routes)
    web_dist = Path(__file__).resolve().parent.parent.parent.parent.parent / "pocketquant-web" / "dist"
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
