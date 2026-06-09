"""Test factory for the pocketquant-bff FastAPI app.

Builds the bff app from its real DI providers wired to testcontainer Settings,
bypassing the module-level ``app = create_app()`` in bff/main.py. Stateless: no
scheduler, no engine — only DB/Cache + the bff handler subset.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from pocketquant.bff.di.container import register_bff_handlers
from pocketquant.bff.di.handlers import BffHandlerProvider
from pocketquant.bff.di.market_data import BffMarketDataProvider
from pocketquant.bff.di.persistence import BffPersistenceProvider
from pocketquant.bff.main_extensions import (
    configure_middleware,
    register_health_checks,
    register_routes,
)
from pocketquant.core.common.logging import setup_logging
from pocketquant.core.common.mediator.mediator import Mediator
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.infrastructure.persistence.mongodb import Database
from pocketquant.infrastructure.persistence.redis import Cache


class TestBffCoreProvider(Provider):
    """Injects a pre-built Settings instance into the bff DI graph for tests.

    Module-level (not a closure) so dishka's get_type_hints() resolves forward
    references on Python 3.14+.
    """

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        return self._settings

    @provide(scope=Scope.APP)
    def get_event_bus(self) -> EventBus:
        return EventBus(max_history=100)

    @provide(scope=Scope.APP)
    def get_mediator(self) -> Mediator:
        return Mediator()


def make_bff_test_app(settings: Settings) -> FastAPI:
    """Build a fully-wired bff FastAPI test app using testcontainer settings."""
    container = make_async_container(
        TestBffCoreProvider(settings),
        BffPersistenceProvider(),
        BffMarketDataProvider(),
        BffHandlerProvider(),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        c = app.state.dishka_container
        try:
            app.state.database = await c.get(Database)
            app.state.cache = await c.get(Cache)
            await register_bff_handlers(c)
            await register_health_checks(c, app)
            yield
        finally:
            await c.close()

    setup_logging(settings)
    app = FastAPI(
        title="pocketquant-bff-test",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    setup_dishka(container, app)
    configure_middleware(app, settings)
    register_routes(app, settings)
    return app
