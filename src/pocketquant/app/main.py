import asyncio
import os
import socket
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka import AsyncContainer
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from pocketquant.app.di import create_container
from pocketquant.app.main_extensions import (
    assert_utc_runtime,
    configure_middleware,
    drain_backtest_tasks,
    ensure_all_indexes,
    init_backtest_tasks,
    register_health_checks,
    register_routes,
    start_loop_lag_probe,
    start_quote_feed,
    stop_loop_lag_probe,
    stop_quote_feed,
    stop_reconcile_loop,
)
from pocketquant.app.roles import (
    hand_over,
    start_trader_lease,
    start_trader_standby,
    start_worker,
    stop_worker,
)
from pocketquant.core.common.logging import get_logger, setup_logging
from pocketquant.core.common.time.simulation import get_current_time
from pocketquant.core.config import get_settings
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.engine.market_data.app_services.sync_jobs import (
    set_container as set_sync_container,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    started_at = time.monotonic()
    settings = get_settings()
    owner = f"{socket.gethostname()}:{os.getpid()}"
    app.state.lease_state = {}
    roles = settings.roles
    logger.info("application_starting", environment=settings.environment, roles=settings.app_roles)

    container: AsyncContainer = app.state.dishka_container

    # Wire the sync-job module container BEFORE any await. JobScheduler is
    # APP-scoped and may resolve+start inside any subsequent `await
    # container.get(...)` chain (e.g. via StrategyAppService during bootstrap).
    # Once started, persisted MongoDBJobStore sync jobs whose next_run_time is
    # within misfire_grace_time can dispatch and call sync_jobs._get_container().
    # Synchronous global assignment — no await means no preemption point.
    set_sync_container(container)

    try:
        assert_utc_runtime()
        start_loop_lag_probe(app)

        # Expose DB/Cache on app.state for middleware hot-path access
        app.state.database = await container.get(Database)
        app.state.cache = await container.get(Cache)

        init_backtest_tasks(app)

        await ensure_all_indexes(container)
        await register_health_checks(container, app)
        if "trader" in roles:
            await start_trader_standby(container, started_at)
            await start_quote_feed(container, app)
            start_trader_lease(container, app, owner)
        if "worker" in roles:
            start_worker(container, app, owner)

        logger.info("application_started")
        yield

    except Exception:
        # Re-raise so FastAPI reports a startup error; the finally block still
        # cancels background tasks and closes the container first.
        logger.exception("application_start_failed")
        raise
    finally:
        # Every drain and stop deadline counts from here.
        started = get_current_time()
        await stop_loop_lag_probe(app)
        # Together, so the next worker starts while this trader drains and neither eats
        # the other's grace.
        results = await asyncio.gather(
            stop_worker(container, app, owner, started),
            hand_over(container, app, owner, started),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                logger.error("application.stop_failed", exc_info=result)
        # Drain (not cancel) lets backtest persistence finish before the engine stops.
        await drain_backtest_tasks(app)
        await stop_reconcile_loop(app)
        if "trader" in roles:
            await stop_quote_feed(container, app)
        # container.close() runs generator cleanup in reverse order:
        # StrategyAppService.stop → JobScheduler.shutdown → Cache/Database.disconnect
        await container.close()
        logger.info("application_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings)

    app = FastAPI(
        # Literal title — settings.app_name varies per env and would leak into
        # the OpenAPI snapshot baseline.
        title="PocketQuant",
        version=settings.app_version,
        description="Algorithmic trading platform — API and trading runtime",
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    # setup_dishka must be called before app starts (adds middleware)
    container = create_container(settings)
    setup_dishka(container, app)

    configure_middleware(app, settings)
    register_routes(app, settings)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("pocketquant.app.main:app", host="0.0.0.0", port=41921)
