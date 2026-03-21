"""Helpers for main.py: middleware, routes, and startup utilities."""

import asyncio
from functools import partial

from dishka import AsyncContainer
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pocketquant.core.common.exceptions import register_exception_handlers
from pocketquant.core.common.health import HealthCoordinator
from pocketquant.core.common.health.checks import check_database, check_redis
from pocketquant.core.common.idempotency import IdempotencyMiddleware
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator.mediator import Mediator
from pocketquant.core.common.rate_limit import RateLimitMiddleware
from pocketquant.core.common.tracing import CorrelationIDMiddleware, RequestLoggingMiddleware
from pocketquant.core.config import Settings
from pocketquant.backtest.handlers import backtest_router
from pocketquant.api.market_data.handlers.quotes.router import router as quote_router
from pocketquant.api.market_data.handlers.router import router as market_data_router
from pocketquant.trading.handlers.strategy import strategy_router
from pocketquant.trading.handlers.trading import trading_router
from pocketquant.core.infrastructure.scheduling.scheduler import JobScheduler
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.persistence.repositories.bar_repository import BarRepository
from pocketquant.backtest.persistence.optimization_repository import (
    OptimizationRepository,
)
from pocketquant.trading.persistence.order_repository import OrderRepository
from pocketquant.trading.persistence.position_repository import PositionRepository
from pocketquant.core.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.persistence.repositories.sync_status_repository import SyncStatusRepository

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
]


# ---------------------------------------------------------------------------
# Lifespan helpers
# ---------------------------------------------------------------------------


async def ensure_all_indexes(container: AsyncContainer) -> None:
    """Ensure MongoDB indexes for all repository collections."""
    repos = [await container.get(rt) for rt in _REPO_TYPES]
    await asyncio.gather(*(repo.ensure_indexes() for repo in repos))
    logger.info("database_indexes_ensured")


async def start_background_jobs(container: AsyncContainer) -> None:
    """Register background sync jobs with the scheduler."""
    settings = await container.get(Settings)
    if not settings.enable_jobs:
        logger.info("background_jobs_disabled")
        return

    from pocketquant.api.market_data.app_services.sync_jobs import register_sync_jobs

    register_sync_jobs(
        mediator=await container.get(Mediator),
        job_scheduler=await container.get(JobScheduler),
        sync_status_repo=await container.get(SyncStatusRepository),
    )
    logger.info("background_jobs_enabled")


async def register_health_checks(
    container: AsyncContainer, app: FastAPI
) -> None:
    """Register health check functions with the coordinator."""
    hc = await container.get(HealthCoordinator)
    hc.register("database", partial(check_database, app.state.database))
    hc.register("redis", partial(check_redis, app.state.cache))


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
    console.print("  -> [cyan]src/main.py[/] in lifespan")
    console.print("  -> [cyan]src/common/database/connection.py[/] in connect")
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
        return job_scheduler.get_jobs()

    api.include_router(market_data_router)
    api.include_router(quote_router)
    api.include_router(strategy_router)
    api.include_router(trading_router)
    api.include_router(backtest_router)

    app.include_router(api)
