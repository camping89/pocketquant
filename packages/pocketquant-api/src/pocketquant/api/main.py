"""PocketQuant application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka import AsyncContainer
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from pocketquant.api.di.container import create_container, register_handlers
from pocketquant.api.main_extensions import (
    configure_middleware,
    ensure_all_indexes,
    handle_startup_failure,
    recover_stale_backtests,
    register_health_checks,
    register_routes,
    start_background_jobs,
    start_quote_feed,
    stop_quote_feed,
)
from pocketquant.api.market_data.app_services.tracked_symbol_seeder import seed_tracked_symbols
from pocketquant.core.common.logging import get_logger, setup_logging
from pocketquant.core.config import get_settings
from pocketquant.core.persistence.mongodb import Database
from pocketquant.core.persistence.redis import Cache

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    logger.info("application_starting", environment=settings.environment)

    container: AsyncContainer = app.state.dishka_container

    try:
        # Expose DB/Cache on app.state for middleware hot-path access
        app.state.database = await container.get(Database)
        app.state.cache = await container.get(Cache)

        await register_handlers(container)
        await ensure_all_indexes(container)
        await recover_stale_backtests(container)
        await seed_tracked_symbols(container)
        await register_health_checks(container, app)
        await start_background_jobs(container)
        await start_quote_feed(container, app)

        logger.info("application_started")
        yield

    except Exception as e:
        handle_startup_failure(e)
    finally:
        await stop_quote_feed(container, app)
        # container.close() runs generator cleanup in reverse order:
        # StrategyAppService.stop → JobScheduler.shutdown → Cache/Database.disconnect
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

    # setup_dishka must be called before app starts (adds middleware)
    container = create_container()
    setup_dishka(container, app)

    configure_middleware(app, settings)
    register_routes(app, settings)

    return app


app = create_app()


def run() -> None:
    """CLI entrypoint for `pocketquant` command."""
    import uvicorn

    uvicorn.run("pocketquant.api.main:app", host="0.0.0.0", port=41920)
