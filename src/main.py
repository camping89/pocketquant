"""PocketQuant - FastAPI Application Entry Point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.common.cache import Cache
from src.common.database import Database
from src.common.jobs import JobScheduler
from src.common.logging import get_logger, setup_logging
from src.config import get_settings
from src.features.market_data.api import router as market_data_router
from src.features.market_data.jobs import register_sync_jobs

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup/shutdown events."""
    settings = get_settings()

    # Startup
    logger.info("application_starting", environment=settings.environment)

    # Connect to databases
    await Database.connect(settings)
    await Cache.connect(settings)

    # Initialize and start job scheduler
    JobScheduler.initialize(settings)
    JobScheduler.start()

    # Register background jobs
    register_sync_jobs()

    logger.info("application_started")

    yield

    # Shutdown
    logger.info("application_stopping")

    JobScheduler.shutdown(wait=True)
    await Cache.disconnect()
    await Database.disconnect()

    logger.info("application_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    # Setup logging first
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

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.environment == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "version": settings.app_version,
            "environment": settings.environment,
        }

    # System info endpoint
    @app.get(f"{settings.api_prefix}/system/jobs")
    async def list_jobs() -> list[dict]:
        """List all scheduled background jobs."""
        return JobScheduler.get_jobs()

    # Include feature routers
    app.include_router(market_data_router, prefix=settings.api_prefix)

    return app


# Create app instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development",
    )
