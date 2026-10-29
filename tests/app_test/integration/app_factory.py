# A plain module, not a conftest, so test files can import it to build a custom app (for
# example with other app_roles).

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka import AsyncContainer
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from pocketquant.app.di import create_container
from pocketquant.app.main_extensions import (
    configure_middleware,
    drain_backtest_tasks,
    ensure_all_indexes,
    init_backtest_tasks,
    register_health_checks,
    register_routes,
)
from pocketquant.core.common.logging import setup_logging
from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.engine.market_data.app_services.sync_jobs import (
    set_container as set_sync_container,
)


# Background jobs belong to the worker role and do not run here.
def make_test_app(settings: Settings) -> FastAPI:
    container = create_container(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        c: AsyncContainer = app.state.dishka_container
        # Mirror main.py: wire the sync-job module container BEFORE any await so
        # that persisted jobs which dispatch during early resolves can find it.
        set_sync_container(c)
        try:
            app.state.database = await c.get(Database)
            app.state.cache = await c.get(Cache)
            init_backtest_tasks(app)
            await ensure_all_indexes(c)
            await register_health_checks(c, app)
            yield
        finally:
            await drain_backtest_tasks(app)
            await c.close()

    setup_logging(settings)
    app = FastAPI(
        title="pocketquant-test",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    setup_dishka(container, app)
    configure_middleware(app, settings)
    register_routes(app, settings)
    return app
