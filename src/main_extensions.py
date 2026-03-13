"""Helpers for main.py: middleware, routes, and startup utilities."""

import asyncio

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.common.exceptions import register_exception_handlers
from src.common.health.checks import check_database, check_redis
from src.common.idempotency import IdempotencyMiddleware
from src.common.logging import get_logger
from src.common.rate_limit import RateLimitMiddleware
from src.common.tracing import CorrelationIDMiddleware, RequestLoggingMiddleware
from src.features.backtesting import backtest_router
from src.features.market_data.quotes.router import router as quote_router
from src.features.market_data.router import router as market_data_router
from src.features.strategy import strategy_router
from src.features.trading import trading_router
from src.services import Services

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan helpers
# ---------------------------------------------------------------------------


async def ensure_all_indexes(services: Services) -> None:
    """Ensure MongoDB indexes for all repository collections."""
    repos = [
        services.order_repository,
        services.position_repository,
        services.backtest_repository,
        services.ohlcv_repository,
        services.sync_status_repository,
        services.symbol_repository,
        services.optimization_repository,
    ]
    await asyncio.gather(*(repo.ensure_indexes() for repo in repos))
    logger.info("database_indexes_ensured")


async def start_background_jobs(services: Services) -> None:
    """Register background sync jobs with the scheduler."""
    if services.settings.enable_jobs:
        from src.application.market_data.sync_jobs import register_sync_jobs

        register_sync_jobs(
            mediator=services.mediator,
            job_scheduler=services.job_scheduler,
            sync_status_repo=services.sync_status_repository,
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


def register_health_checks(services: Services, app: FastAPI) -> None:
    """Register health check functions with the coordinator.

    Called from lifespan after Services is built, so all dependencies are available.
    """
    hc = services.health_coordinator

    async def _check_db() -> dict:
        return await check_database(app.state.database)

    async def _check_redis() -> dict:
        return await check_redis(app.state.cache)

    hc.register("database", _check_db)
    hc.register("redis", _check_redis)


def register_routes(app: FastAPI, settings) -> None:
    """Register health/system endpoints and all feature routers."""

    @app.get("/health")
    async def health_check(request: Request) -> dict:
        services: Services = request.app.state.services
        result = await services.health_coordinator.check_all()
        result["version"] = settings.app_version
        result["environment"] = settings.environment
        return result

    api = APIRouter(prefix=settings.api_prefix)

    @api.get("/system/jobs")
    async def list_jobs(request: Request) -> list[dict]:
        return request.app.state.services.job_scheduler.get_jobs()

    api.include_router(market_data_router)
    api.include_router(quote_router)
    api.include_router(strategy_router)
    api.include_router(trading_router)
    api.include_router(backtest_router)

    app.include_router(api)
