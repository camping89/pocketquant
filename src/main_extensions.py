"""Helpers for main.py: middleware, routes, and startup utilities."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.common.health.checks import check_database, check_redis
from src.common.idempotency import IdempotencyMiddleware
from src.common.logging import get_logger
from src.common.rate_limit import RateLimitMiddleware
from src.common.tracing import CorrelationIDMiddleware, RequestLoggingMiddleware
from src.container import AppContainer
from src.features.backtesting import backtest_router
from src.features.market_data.quotes.router import router as quote_router
from src.features.market_data.router import router as market_data_router
from src.features.strategy import strategy_router
from src.features.trading import trading_router

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan helpers
# ---------------------------------------------------------------------------


async def ensure_all_indexes(container: AppContainer) -> None:
    """Ensure MongoDB indexes for all repository collections."""
    await container.order_repository().ensure_indexes()
    await container.position_repository().ensure_indexes()
    await container.backtest_repository().ensure_indexes()
    await container.ohlcv_repository().ensure_indexes()
    await container.sync_status_repository().ensure_indexes()
    await container.symbol_repository().ensure_indexes()
    await container.optimization_repository().ensure_indexes()
    logger.info("database_indexes_ensured")


def start_background_jobs(container: AppContainer) -> None:
    """Register background sync jobs with the scheduler from container."""
    settings = container.settings()
    if settings.enable_jobs:
        from src.application.market_data.sync_jobs import register_sync_jobs

        register_sync_jobs(
            mediator=container.mediator(),
            job_scheduler=container.job_scheduler(),
            sync_status_repo=container.sync_status_repository(),
        )
        logger.info("background_jobs_enabled")
    else:
        logger.info("background_jobs_disabled")


def handle_startup_failure(error: Exception) -> None:
    """Display a rich error panel and hard-exit on startup failure."""
    import os

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
    console.print("  → [cyan]src/main.py[/] in lifespan")
    console.print("  → [cyan]src/common/database/connection.py[/] in connect")
    os._exit(1)


# ---------------------------------------------------------------------------
# App factory helpers
# ---------------------------------------------------------------------------


def configure_middleware(app: FastAPI, settings) -> None:
    """Attach all middleware layers to the application."""
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


def register_routes(app: FastAPI, container: AppContainer, settings) -> None:
    """Register health/system endpoints and all feature routers."""
    health_coordinator = container.health_coordinator()
    # Lazy resolution: container.database()/cache() resolved at check time (after init_resources)
    health_coordinator.register("database", lambda: check_database(container.database()))
    health_coordinator.register("redis", lambda: check_redis(container.cache()))

    @app.get("/health")
    async def health_check() -> dict:
        result = await health_coordinator.check_all()
        result["version"] = settings.app_version
        result["environment"] = settings.environment
        return result

    api = APIRouter(prefix=settings.api_prefix)

    @api.get("/system/jobs")
    async def list_jobs() -> list[dict]:
        container: AppContainer = app.state.container
        return container.job_scheduler().get_jobs()

    api.include_router(market_data_router)
    api.include_router(quote_router)
    api.include_router(strategy_router)
    api.include_router(trading_router)
    api.include_router(backtest_router)

    app.include_router(api)
