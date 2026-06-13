"""PocketQuant application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka import AsyncContainer
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from pocketquant.app.di.container import create_container
from pocketquant.app.main_extensions import (
    configure_middleware,
    ensure_all_indexes,
    handle_startup_failure,
    migrate_backtest_request_ids,
    migrate_backtest_run_cache_ids,
    migrate_job_history_uuid_ids,
    migrate_strategy_id_fields,
    migrate_subscription_desired_state,
    migrate_subscription_uuid_ids,
    migrate_tracked_symbols_uuid_ids,
    recover_orphan_jobs,
    recover_stale_backtests,
    register_health_checks,
    register_routes,
    rehydrate_strategies_from_subscriptions,
    start_background_jobs,
    start_backtest_worker,
    start_quote_feed,
    start_reconcile_loop,
    stop_backtest_worker,
    stop_quote_feed,
    stop_reconcile_loop,
)
from pocketquant.app.market_data.app_services.tracked_symbol_seeder import seed_tracked_symbols
from pocketquant.core.common.logging import get_logger, setup_logging
from pocketquant.core.config import get_settings
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.engine.market_data.app_services.sync_jobs import (
    set_container as set_sync_container,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    logger.info("application_starting", environment=settings.environment)

    container: AsyncContainer = app.state.dishka_container

    # Wire the sync-job module container BEFORE any await. JobScheduler is
    # APP-scoped and may resolve+start inside any subsequent `await
    # container.get(...)` chain (e.g. via StrategyAppService during rehydrate).
    # Once started, persisted MongoDBJobStore sync jobs whose next_run_time is
    # within misfire_grace_time can dispatch and call sync_jobs._get_container().
    # Synchronous global assignment — no await means no preemption point.
    set_sync_container(container)

    try:
        # Expose DB/Cache on app.state for middleware hot-path access
        app.state.database = await container.get(Database)
        app.state.cache = await container.get(Cache)

        # Migration must precede service resolution — PositionAppService.start()
        # loads open positions with the post-migration field shape. If legacy
        # docs are still on disk, the read would crash before migration fixed them.
        await migrate_strategy_id_fields(container)
        # Backfill desired_state/actual_state right after the field rename — both
        # are subscriptions-collection migrations; rename first, then state backfill,
        # so rehydrate/reconcile read the final field shape.
        await migrate_subscription_desired_state(container)
        # Re-key tracked_symbols._id to uuid7 BEFORE seed_tracked_symbols runs,
        # so the seeder's upserts never race legacy symbol-keyed docs.
        await migrate_tracked_symbols_uuid_ids(container)
        # Re-key legacy ObjectId docs in the append-only job_history log; new
        # writes are already uuid7, so this only touches pre-uuid history.
        await migrate_job_history_uuid_ids(container)
        # Re-key bt:{sub_id} backtest requests to uuid7. Creates the pending-sub
        # partial unique index FIRST so the dedup guarantee never lapses, and
        # runs BEFORE the backtest worker starts draining the queue.
        await migrate_backtest_request_ids(container)
        # Re-key per-subscription cache docs in backtest_runs (_id == sub_id) to
        # uuid7. Ensures the subscription_id unique index FIRST so the one-doc-
        # per-sub guarantee never lapses, and runs BEFORE the worker writes caches.
        await migrate_backtest_run_cache_ids(container)
        # Re-key subscriptions._id (sha256 16-hex) to uuid7 + rewrite the 4 FK
        # fields, map-based and crash-safe. Runs LAST of the id migrations —
        # phases above already decoupled every other _id from sub_id — and
        # BEFORE rehydrate so RAM instance keys are minted from the new ids.
        await migrate_subscription_uuid_ids(container)
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
        await start_backtest_worker(container, app)

        logger.info("application_started")
        yield

    except Exception as e:
        handle_startup_failure(e)
    finally:
        # Stop worker + reconcile FIRST — before quote feed and container.close()
        # (which stops StrategyAppService) — so neither dispatches against a
        # stopping engine.
        await stop_backtest_worker(container, app)
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
        # Literal title — settings.app_name varies per env and would leak into
        # the OpenAPI snapshot baseline.
        title="PocketQuant",
        version=settings.app_version,
        description="Algorithmic trading platform — API, SPA serving, and trading runtime",
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

    uvicorn.run("pocketquant.app.main:app", host="0.0.0.0", port=41921)
