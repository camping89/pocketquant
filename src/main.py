from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.common.cache import Cache
from src.common.database import Database
from src.common.health import HealthCoordinator, check_database, check_redis
from src.common.idempotency import IdempotencyMiddleware
from src.common.jobs import JobScheduler
from src.common.logging import get_logger, setup_logging
from src.common.mediator import Mediator
from src.common.messaging import EventBus
from src.common.rate_limit import RateLimitMiddleware
from src.common.tracing import CorrelationIDMiddleware
from src.config import get_settings
from src.features.market_data.api import quote_router
from src.features.market_data.api import router as market_data_router
from src.features.market_data.jobs import register_sync_jobs, set_mediator
from src.features.market_data.ohlcv import GetOHLCVHandler, GetOHLCVQuery
from src.features.market_data.quote import (
    GetAllQuotesHandler,
    GetAllQuotesQuery,
    GetLatestQuoteHandler,
    GetLatestQuoteQuery,
    StartQuoteFeedCommand,
    StartQuoteFeedHandler,
    StopQuoteFeedCommand,
    StopQuoteFeedHandler,
    SubscribeCommand,
    SubscribeHandler,
    UnsubscribeCommand,
    UnsubscribeHandler,
)
from src.features.market_data.status import (
    GetQuoteServiceStatusHandler,
    GetQuoteServiceStatusQuery,
    GetSymbolSyncStatusHandler,
    GetSymbolSyncStatusQuery,
    GetSyncStatusHandler,
    GetSyncStatusQuery,
)
from src.features.market_data.sync import (
    BulkSyncCommand,
    BulkSyncHandler,
    SyncSymbolCommand,
    SyncSymbolHandler,
)
from src.infrastructure.tradingview import TradingViewProvider

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    logger.info("application_starting", environment=settings.environment)

    mediator = Mediator()
    event_bus = EventBus(max_history=100)

    app.state.mediator = mediator
    app.state.event_bus = event_bus

    try:
        await Database.connect(settings)
        await Cache.connect(settings)

        if settings.enable_jobs:
            JobScheduler.initialize(settings)
            JobScheduler.start()
            register_sync_jobs()
            logger.info("background_jobs_enabled")
        else:
            logger.info("background_jobs_disabled")

        tv_provider = TradingViewProvider(settings)

        sync_handler = SyncSymbolHandler(tv_provider, event_bus)
        mediator.register(SyncSymbolCommand, sync_handler)
        mediator.register(BulkSyncCommand, BulkSyncHandler(sync_handler))

        mediator.register(GetOHLCVQuery, GetOHLCVHandler())

        mediator.register(StartQuoteFeedCommand, StartQuoteFeedHandler(settings))
        mediator.register(StopQuoteFeedCommand, StopQuoteFeedHandler(settings))
        mediator.register(SubscribeCommand, SubscribeHandler(settings))
        mediator.register(UnsubscribeCommand, UnsubscribeHandler(settings))
        mediator.register(GetLatestQuoteQuery, GetLatestQuoteHandler())
        mediator.register(GetAllQuotesQuery, GetAllQuotesHandler(settings))

        mediator.register(GetSyncStatusQuery, GetSyncStatusHandler())
        mediator.register(GetSymbolSyncStatusQuery, GetSymbolSyncStatusHandler())
        mediator.register(
            GetQuoteServiceStatusQuery, GetQuoteServiceStatusHandler(settings)
        )

        set_mediator(mediator)

    except Exception as e:
        import os

        from rich.console import Console
        from rich.panel import Panel

        console = Console(stderr=True)
        console.print(
            Panel(
                f"[bold red]{type(e).__name__}[/]: {e}",
                title="Startup Failed",
                border_style="red",
            )
        )
        console.print("\n[dim]Your code:[/]")
        console.print("  → [cyan]src/main.py:24[/] in lifespan")
        console.print("  → [cyan]src/common/database/connection.py:32[/] in connect")
        os._exit(1)

    logger.info("application_started")
    yield
    logger.info("application_stopping")

    if settings.enable_jobs:
        JobScheduler.shutdown(wait=True)
        
    await Cache.disconnect()
    await Database.disconnect()

    logger.info("application_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Algorithmic trading platform with backtesting and forward testing",
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.environment == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(RateLimitMiddleware, capacity=200, refill_rate=20.0)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(CorrelationIDMiddleware)

    health_coordinator = HealthCoordinator(timeout=5.0)
    health_coordinator.register("database", check_database)
    health_coordinator.register("redis", check_redis)

    @app.get("/health")
    async def health_check() -> dict:
        result = await health_coordinator.check_all()
        result["version"] = settings.app_version
        result["environment"] = settings.environment
        return result

    @app.get(f"{settings.api_prefix}/system/jobs")
    async def list_jobs() -> list[dict]:
        return JobScheduler.get_jobs()

    app.include_router(market_data_router, prefix=settings.api_prefix)
    app.include_router(quote_router, prefix=settings.api_prefix)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development",
    )
