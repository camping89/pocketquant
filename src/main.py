"""PocketQuant application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.common.logging import get_logger, setup_logging
from src.container import AppContainer, register_all_handlers
from src.main_extensions import (
    configure_middleware,
    ensure_all_indexes,
    handle_startup_failure,
    register_routes,
    start_background_jobs,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    container: AppContainer = app.state.container
    settings = container.settings()
    logger.info("application_starting", environment=settings.environment)

    try:
        # Initialize all Resource providers in dependency order:
        # database → cache → job_scheduler → order_manager → position_tracker → strategy_engine
        await container.init_resources()  # type: ignore[misc]  # async Resource providers return awaitable at runtime

        # Post-init: indexes, handler registration, background jobs
        await ensure_all_indexes(container)
        register_all_handlers(container)
        start_background_jobs(container)
    except Exception as e:
        await container.shutdown_resources()  # type: ignore[misc]
        handle_startup_failure(e)

    logger.info("application_started")
    yield
    logger.info("application_stopping")

    # Shutdown all Resources in reverse order (strategy_engine → ... → database)
    await container.shutdown_resources()  # type: ignore[misc]
    logger.info("application_stopped")


def create_app() -> FastAPI:
    container = AppContainer()
    settings = container.settings()
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

    app.state.container = container
    configure_middleware(app, settings)
    register_routes(app, container, settings)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    from src.config import get_settings

    _settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=_settings.api_host,
        port=_settings.api_port,
        reload=_settings.environment == "development",
    )
