from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.common.cache import Cache
from src.common.database import Database
from src.common.logging import get_logger, setup_logging
from src.common.mediator import Mediator
from src.common.messaging import EventBus
from src.config import get_settings
from src.infrastructure import JobScheduler
from src.main_extensions import (
    configure_middleware,
    ensure_all_indexes,
    handle_startup_failure,
    init_trading_subsystem,
    register_routes,
    start_background_jobs,
)

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
        await ensure_all_indexes()
        start_background_jobs(settings)
        await init_trading_subsystem(app, mediator, event_bus, settings)
    except Exception as e:
        handle_startup_failure(e)

    logger.info("application_started")
    yield
    logger.info("application_stopping")
    await shutdown(app, settings)


async def shutdown(app: FastAPI, settings) -> None:
    """Graceful shutdown: stop engine, scheduler, and disconnect stores."""
    await app.state.strategy_engine.stop()
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

    configure_middleware(app, settings)
    register_routes(app, settings)

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
