"""Helpers for main.py: lifespan lifecycle, middleware, and route registration."""

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from src.application.market_data.sync_jobs import register_sync_jobs, set_mediator
from src.common.cache import Cache
from src.common.database import Database
from src.common.health import HealthCoordinator, check_database, check_redis
from src.common.idempotency import IdempotencyMiddleware
from src.common.jobs import JobScheduler
from src.common.logging import get_logger
from src.common.rate_limit import RateLimitMiddleware
from src.common.tracing import CorrelationIDMiddleware, RequestLoggingMiddleware
from src.features.backtesting import backtest_router
from src.features.backtesting.register import register_handlers as register_backtesting
from src.features.market_data.quotes.router import router as quote_router
from src.features.market_data.register import register_handlers as register_market_data
from src.features.market_data.router import router as market_data_router
from src.features.risk import RiskCheckHandler
from src.features.strategy import StrategyEngine, strategy_router
from src.features.strategy.register import register_handlers as register_strategy
from src.features.trading import OrderManager, PositionTracker, trading_router
from src.features.trading.register import register_handlers as register_trading
from src.infrastructure.brokers import BrokerFactory
from src.infrastructure.tradingview import TradingViewProvider
from src.persistence.repositories.backtest_repository import BacktestRepository
from src.persistence.repositories.ohlcv_repository import OHLCVRepository
from src.persistence.repositories.optimization_repository import OptimizationRepository
from src.persistence.repositories.order_repository import OrderRepository
from src.persistence.repositories.position_repository import PositionRepository
from src.persistence.repositories.symbol_repository import SymbolRepository
from src.persistence.repositories.sync_status_repository import SyncStatusRepository

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan helpers
# ---------------------------------------------------------------------------


async def ensure_all_indexes() -> None:
    """Ensure MongoDB indexes for all repository collections."""
    await OrderRepository.ensure_indexes()
    await PositionRepository.ensure_indexes()
    await BacktestRepository.ensure_indexes()
    await OHLCVRepository.ensure_indexes()
    await SyncStatusRepository.ensure_indexes()
    await SymbolRepository.ensure_indexes()
    await OptimizationRepository.ensure_indexes()
    logger.info("database_indexes_ensured")


def start_background_jobs(settings) -> None:
    """Initialize and start the background job scheduler."""
    if settings.enable_jobs:
        JobScheduler.initialize(settings)
        JobScheduler.start()
        register_sync_jobs()
        logger.info("background_jobs_enabled")
    else:
        logger.info("background_jobs_disabled")


async def init_trading_subsystem(app: FastAPI, mediator, event_bus, settings) -> None:
    """Set up strategy engine, trading components, and register all CQRS handlers."""
    tv_provider = TradingViewProvider(settings)

    # Register market-data CQRS handlers (auto-discovered via @handles)
    register_market_data(
        mediator,
        settings=settings,
        tv_provider=tv_provider,
        event_bus=event_bus,
    )

    # Build trading components
    broker_factory = BrokerFactory()
    order_manager = OrderManager(event_bus)
    position_tracker = PositionTracker(event_bus)
    risk_handler = RiskCheckHandler()

    default_broker_config = {
        "initial_balance": settings.paper_initial_balance,
        "slippage_percent": settings.paper_slippage_percent,
        "api_key": settings.okx_api_key,
        "api_secret": settings.okx_api_secret,
        "passphrase": settings.okx_passphrase,
        "demo": settings.okx_demo_mode,
    }

    strategy_engine = StrategyEngine(
        event_bus=event_bus,
        broker_factory=broker_factory,
        order_manager=order_manager,
        position_tracker=position_tracker,
        risk_handler=risk_handler,
        default_broker_config=default_broker_config,
    )

    app.state.strategy_engine = strategy_engine
    app.state.order_manager = order_manager
    app.state.position_tracker = position_tracker

    # Register strategy handlers and start components
    register_strategy(mediator, strategy_engine=strategy_engine)
    await order_manager.load_pending_orders()
    await position_tracker.start()
    await strategy_engine.start()
    logger.info("strategy_engine_initialized")

    # Register remaining CQRS handlers
    register_trading(
        mediator,
        order_manager=order_manager,
        position_tracker=position_tracker,
    )
    register_backtesting(
        mediator,
        event_bus=event_bus,
        strategy_engine=strategy_engine,
    )
    set_mediator(mediator)


def handle_startup_failure(error: Exception) -> None:
    """Display a rich error panel and hard-exit on startup failure."""
    import os

    from rich.console import Console
    from rich.panel import Panel

    console = Console(stderr=True)
    console.print(
        Panel(
            f"[bold red]{type(error).__name__}[/]: {error}",
            title="Startup Failed",
            border_style="red",
        )
    )
    console.print("\n[dim]Your code:[/]")
    console.print("  → [cyan]src/main.py[/] in lifespan")
    console.print("  → [cyan]src/common/database/connection.py[/] in connect")
    os._exit(1)


async def shutdown(app: FastAPI, settings) -> None:
    """Graceful shutdown: stop engine, scheduler, and disconnect stores."""
    await app.state.strategy_engine.stop()
    if settings.enable_jobs:
        JobScheduler.shutdown(wait=True)
    await Cache.disconnect()
    await Database.disconnect()
    logger.info("application_stopped")


# ---------------------------------------------------------------------------
# App factory helpers
# ---------------------------------------------------------------------------


def configure_middleware(app: FastAPI, settings) -> None:
    """Attach all middleware layers to the application."""
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


def register_routes(app: FastAPI, settings) -> None:
    """Register health/system endpoints and all feature routers."""
    health_coordinator = HealthCoordinator(timeout=5.0)
    health_coordinator.register("database", check_database)
    health_coordinator.register("redis", check_redis)

    @app.get("/health")
    async def health_check() -> dict:
        result = await health_coordinator.check_all()
        result["version"] = settings.app_version
        result["environment"] = settings.environment
        return result

    api = APIRouter(prefix=settings.api_prefix)
    @api.get("/system/jobs")
    async def list_jobs() -> list[dict]:
        return JobScheduler.get_jobs()
    api.include_router(market_data_router)
    api.include_router(quote_router)
    api.include_router(strategy_router)
    api.include_router(trading_router)
    api.include_router(backtest_router)

    app.include_router(api)
