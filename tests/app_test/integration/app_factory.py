"""Shared test app factory for pocketquant-app integration tests.

Exported as a plain module (not conftest) so it can be imported by test files
that need to build a custom app instance (e.g. with enable_jobs=True).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from pocketquant.app.di import (
    AppTradingServiceProvider,
    BacktestWorkerProvider,
    ExecutionProvider,
    HandlerProvider,
    InfrastructureProvider,
    MarketDataProvider,
    PersistenceProvider,
)
from pocketquant.app.di.container import register_handlers
from pocketquant.app.main_extensions import (
    configure_middleware,
    ensure_all_indexes,
    handle_startup_failure,
    migrate_strategy_id_fields,
    recover_stale_backtests,
    register_health_checks,
    register_routes,
    start_background_jobs,
    start_backtest_worker,
    stop_backtest_worker,
)
from pocketquant.core.common.logging import setup_logging
from pocketquant.core.common.mediator.mediator import Mediator
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.engine.market_data.app_services.sync_jobs import (
    set_container as set_sync_container,
)


class TestCoreProvider(Provider):
    """Module-level provider that injects a pre-built Settings instance.

    Defined here (not inside a function) so dishka's get_type_hints() can
    resolve forward references correctly on Python 3.14+.
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


def make_test_app(settings: Settings) -> FastAPI:
    """Build a fully-wired FastAPI test app using testcontainer settings.

    Identical lifecycle to production: indexes, stale recovery, health checks,
    background jobs (enabled only if settings.enable_jobs=True).
    """
    providers = [
        TestCoreProvider(settings),
        PersistenceProvider(),
        InfrastructureProvider(),
        ExecutionProvider(),
        MarketDataProvider(),
        AppTradingServiceProvider(),
        HandlerProvider(),
        BacktestWorkerProvider(),
    ]
    container = make_async_container(*providers)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        c: AsyncContainer = app.state.dishka_container
        # Mirror main.py: wire the sync-job module container BEFORE any await so
        # that persisted jobs which dispatch during early resolves can find it.
        set_sync_container(c)
        try:
            app.state.database = await c.get(Database)
            app.state.cache = await c.get(Cache)
            # Mirror main.py: migration BEFORE handler registration so that
            # PositionAppService.load_open_positions() reads post-migration shape.
            await migrate_strategy_id_fields(c)
            await register_handlers(c)
            await ensure_all_indexes(c)
            await recover_stale_backtests(c)
            await register_health_checks(c, app)
            await start_background_jobs(c)
            await start_backtest_worker(c, app)
            yield
        except Exception as e:
            handle_startup_failure(e)
        finally:
            await stop_backtest_worker(c, app)
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
