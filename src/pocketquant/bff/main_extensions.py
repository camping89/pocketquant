"""bff startup helpers: middleware, routes, and health checks."""

from functools import partial
from pathlib import Path
from typing import Any

from dishka import AsyncContainer
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pocketquant.core.common.exceptions import register_exception_handlers
from pocketquant.core.common.health import HealthCoordinator
from pocketquant.core.common.idempotency import IdempotencyMiddleware
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.rate_limit import RateLimitMiddleware
from pocketquant.core.common.tracing import CorrelationIDMiddleware, RequestLoggingMiddleware
from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.health_checks import check_database, check_redis
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)

logger = get_logger(__name__)


async def register_health_checks(container: AsyncContainer, app: FastAPI) -> None:
    """Register DB + Redis health checks with the coordinator."""
    hc = await container.get(HealthCoordinator)
    hc.register("database", partial(check_database, app.state.database))
    hc.register("redis", partial(check_redis, app.state.cache))


def configure_middleware(app: FastAPI, settings: Settings) -> None:
    """Attach all middleware layers and global exception handlers."""
    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.environment == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, capacity=200, refill_rate=20.0)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(CorrelationIDMiddleware)


async def _list_jobs_from_mongo(
    database: Database, history_repo: JobHistoryRepository
) -> list[dict[str, Any]]:
    """Read apscheduler_jobs + job_history without a running scheduler.

    apscheduler_jobs stores serialised APScheduler job docs. We read raw Mongo
    docs and project only the stable fields (id, next_run_time, func_ref). The
    func_ref is stored as ``func`` in the APScheduler MongoDBJobStore pickled
    payload — we skip deserialisation and expose only the last-run enrichment
    from job_history instead.
    """
    coll = database.database["apscheduler_jobs"]
    raw_jobs = await coll.find({}, {"_id": 1, "next_run_time": 1}).to_list(length=200)

    job_ids = [doc["_id"] for doc in raw_jobs]
    last_runs: dict[str, dict[str, Any]] = {}
    if job_ids:
        try:
            last_runs = await history_repo.get_latest_by_job_ids(job_ids)
        except Exception:
            logger.warning("bff.system_jobs.last_runs_failed", exc_info=True)

    result = []
    for doc in raw_jobs:
        job_id = doc["_id"]
        next_run = doc.get("next_run_time")
        entry: dict[str, Any] = {
            "id": job_id,
            "next_run": next_run.isoformat() if next_run else None,
            "last_run": last_runs.get(job_id),
        }
        result.append(entry)
    return result


def register_routes(app: FastAPI, settings: Settings) -> None:
    """Register health endpoint and all feature routers."""
    from pocketquant.bff.routes.backtest import backtest_router, run_all_backtests_router
    from pocketquant.bff.routes.market_data import router as market_data_router
    from pocketquant.bff.routes.market_data_quotes import router as quote_router
    from pocketquant.bff.routes.strategy import strategy_router, subscription_router
    from pocketquant.bff.routes.tracked_symbols import router as tracked_symbols_router
    from pocketquant.bff.routes.trading_orders_positions import trading_router

    @app.get("/health")
    @inject
    async def health_check(
        health_coordinator: FromDishka[HealthCoordinator],
    ) -> dict:
        result = await health_coordinator.check_all()
        result["version"] = settings.app_version
        result["environment"] = settings.environment
        return result

    api = APIRouter(prefix=settings.api_prefix, route_class=DishkaRoute)

    @api.get("/system/jobs")
    async def list_jobs(
        database: FromDishka[Database],
        history_repo: FromDishka[JobHistoryRepository],
    ) -> list[dict]:
        # bff has no running JobScheduler — read the APScheduler Mongo store directly.
        return await _list_jobs_from_mongo(database, history_repo)

    from pocketquant.bff.system_jobs.route import router as system_jobs_router

    api.include_router(market_data_router)
    api.include_router(tracked_symbols_router, prefix="/market-data")
    api.include_router(quote_router)
    api.include_router(system_jobs_router)
    api.include_router(strategy_router)
    api.include_router(run_all_backtests_router)
    api.include_router(subscription_router)
    api.include_router(trading_router)
    api.include_router(backtest_router)

    app.include_router(api)

    # StaticFiles + SPA fallback — after API routes so /api/* is never intercepted
    # repo root = 4 levels up from src/pocketquant/bff/main_extensions.py
    web_dist = Path(__file__).resolve().parents[3] / "packages" / "pocketquant-web" / "dist"
    if web_dist.is_dir():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="static-assets")

        @app.get("/{path:path}")
        async def spa_fallback(path: str) -> FileResponse:
            """Serve index.html for all non-API routes (SPA fallback)."""
            file = web_dist / path
            if file.is_file():
                return FileResponse(file)
            return FileResponse(web_dist / "index.html")

        logger.info("spa_mounted", path=str(web_dist))
