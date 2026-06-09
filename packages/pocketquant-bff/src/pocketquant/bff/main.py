"""PocketQuant BFF entry point — stateless FE gateway.

Lifespan: connect MongoDB + Redis, register bff handler subset with Mediator,
register health checks. No migrations, no scheduler, no WS, no reconcile loop.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka import AsyncContainer
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from pocketquant.bff.di.container import create_bff_container, register_bff_handlers
from pocketquant.bff.main_extensions import (
    configure_middleware,
    register_health_checks,
    register_routes,
)
from pocketquant.core.common.logging import get_logger, setup_logging
from pocketquant.core.config import get_settings
from pocketquant.infrastructure.persistence.mongodb import Database
from pocketquant.infrastructure.persistence.redis import Cache

logger = get_logger(__name__)

BFF_PORT = 41921


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    logger.info("bff_starting", environment=settings.environment)

    container: AsyncContainer = app.state.dishka_container

    try:
        app.state.database = await container.get(Database)
        app.state.cache = await container.get(Cache)

        await register_bff_handlers(container)
        await register_health_checks(container, app)

        logger.info("bff_started")
        yield

    except Exception as e:
        from rich.console import Console
        from rich.panel import Panel

        Console(stderr=True).print(
            Panel(
                f"[bold red]{type(e).__name__}[/]: {e}",
                title="BFF Startup Failed",
                border_style="red",
            )
        )
        raise
    finally:
        await container.close()
        logger.info("bff_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings)

    app = FastAPI(
        title="PocketQuant BFF",
        version=settings.app_version,
        description="FE gateway — stateless FastAPI serving pocketquant-web + DB read/write",
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    container = create_bff_container()
    setup_dishka(container, app)

    configure_middleware(app, settings)
    register_routes(app, settings)

    return app


app = create_app()


def run() -> None:
    """CLI entrypoint for `pocketquant-bff` command."""
    import os

    import uvicorn

    port = int(os.environ.get("BFF_PORT", BFF_PORT))
    uvicorn.run("pocketquant.bff.main:app", host="0.0.0.0", port=port)
