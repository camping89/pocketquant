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
    migrate_strategy_id_fields,
    migrate_subscription_desired_state,
    recover_orphan_jobs,
    recover_stale_backtests,
    register_health_checks,
    register_routes,
    rehydrate_strategies_from_subscriptions,
    rekey_backtest_job_refs,
    start_background_jobs,
    start_quote_feed,
    start_reconcile_loop,
    stop_quote_feed,
    stop_reconcile_loop,
)
from pocketquant.api.market_data.app_services.sync_jobs import set_container as set_sync_container
from pocketquant.api.market_data.app_services.tracked_symbol_seeder import seed_tracked_symbols
from pocketquant.backtest.jobs.subscription_backtest_jobs import (
    set_container as set_backtest_container,
)
from pocketquant.core.common.logging import get_logger, setup_logging
from pocketquant.core.config import get_settings
from pocketquant.infrastructure.persistence.mongodb import Database
from pocketquant.infrastructure.persistence.redis import Cache

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    logger.info("application_starting", environment=settings.environment)

    container: AsyncContainer = app.state.dishka_container

    # Wire job-module containers BEFORE any await. JobScheduler is APP-scoped and
    # may resolve+start inside any subsequent `await container.get(...)` chain
    # (e.g. via StrategyAppService during rehydrate). Once started, persisted
    # MongoDBJobStore jobs whose next_run_time is within misfire_grace_time can
    # dispatch and call sync_jobs._get_container() / backtest_jobs._get_container().
    # Synchronous global assignments — no await means no preemption point.
    set_sync_container(container)
    set_backtest_container(container)

    try:
        # Expose DB/Cache on app.state for middleware hot-path access
        app.state.database = await container.get(Database)
        app.state.cache = await container.get(Cache)

        # Migration must precede register_handlers — handler resolution
        # cascade-instantiates PositionAppService.start() which loads open
        # positions with the post-migration field shape. If legacy docs are
        # still on disk, the read would crash before migration could fix them.
        await migrate_strategy_id_fields(container)
        # Backfill desired_state/actual_state right after the field rename — both
        # are subscriptions-collection migrations; rename first, then state backfill,
        # so rehydrate/reconcile read the final field shape.
        await migrate_subscription_desired_state(container)
        # Re-key moved bt:* job refs BEFORE register_handlers — that cascade can
        # start JobScheduler, which would resolve+drop a stale (old-ref) job.
        await rekey_backtest_job_refs(container)
        await register_handlers(container)
        await ensure_all_indexes(container)
        await recover_stale_backtests(container)
        await recover_orphan_jobs(container)
        await seed_tracked_symbols(container)
        await rehydrate_strategies_from_subscriptions(container)
        await register_health_checks(container, app)
        await start_background_jobs(container)
        await start_quote_feed(container, app)
        # Start LAST — instances are rehydrated, so the first tick has no spurious
        # missing_instance warnings.
        await start_reconcile_loop(container, app)

        logger.info("application_started")
        yield

    except Exception as e:
        handle_startup_failure(e)
    finally:
        # Stop reconcile FIRST — before quote feed and container.close() (which
        # stops StrategyAppService) — so it never issues start/stop on a stopping engine.
        await stop_reconcile_loop(container, app)
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
