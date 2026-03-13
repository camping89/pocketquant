"""PocketQuant application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from src.common.logging import get_logger, setup_logging
from src.config import get_settings
from src.container import create_container, register_handlers
from src.main_extensions import (
    configure_middleware,
    ensure_all_indexes,
    handle_startup_failure,
    register_health_checks,
    register_routes,
    start_background_jobs,
)
from src.persistence.mongodb import Database
from src.persistence.redis import Cache

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    logger.info("application_starting", environment=settings.environment)

    container = create_container()

    try:
        # Expose DB/Cache on app.state for middleware hot-path access
        app.state.database = await container.get(Database)
        app.state.cache = await container.get(Cache)

        await register_handlers(container)
        await ensure_all_indexes(container)
        await register_health_checks(container, app)
        await start_background_jobs(container)

        setup_dishka(container, app)

        logger.info("application_started")
        yield

    except Exception as e:
        handle_startup_failure(e)
    finally:
        # container.close() runs generator cleanup in reverse order:
        # StrategyEngine.stop → JobScheduler.shutdown → Cache/Database.disconnect
        await container.close()
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
