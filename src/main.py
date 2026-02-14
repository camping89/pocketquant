from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.application.market_data.sync_jobs import register_sync_jobs, set_mediator
from src.common.cache import Cache
from src.common.database import Database
from src.common.health import HealthCoordinator, check_database, check_redis
from src.common.idempotency import IdempotencyMiddleware
from src.common.jobs import JobScheduler
from src.common.logging import get_logger, setup_logging
from src.common.mediator import Mediator
from src.common.messaging import EventBus
from src.common.rate_limit import RateLimitMiddleware
from src.common.tracing import CorrelationIDMiddleware, RequestLoggingMiddleware
from src.config import get_settings
from src.features.backtesting import backtest_router

# Feature handler registrations (auto-discover via @handles decorator)
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
from src.infrastructure.persistence.repositories.backtest_repository import BacktestRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.position_repository import PositionRepository
from src.infrastructure.tradingview import TradingViewProvider

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    logger.info("application_starting", environment=settings.environment)

    mediator = Mediator()
    event_bus = EventBus(max_history=100)

    app.state.mediator = mediator
    app.state.event_bus = event_bus

    try:
        await Database.connect(settings)
        await Cache.connect(settings)

        # Ensure MongoDB indexes for trading collections
        await OrderRepository.ensure_indexes()
        await PositionRepository.ensure_indexes()
        await BacktestRepository.ensure_indexes()
        logger.info("trading_indexes_ensured")

        if settings.enable_jobs:
            JobScheduler.initialize(settings)
            JobScheduler.start()
            register_sync_jobs()
            logger.info("background_jobs_enabled")
        else:
            logger.info("background_jobs_disabled")

        tv_provider = TradingViewProvider(settings)

        # === Register all CQRS handlers (auto-discovered via @handles) ===
        register_market_data(
            mediator,
            settings=settings,
            tv_provider=tv_provider,
            event_bus=event_bus,
        )

        # === Strategy Engine Setup ===
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

        register_strategy(mediator, strategy_engine=strategy_engine)

        # Load pending orders from database
        await order_manager.load_pending_orders()

        # Start position tracker (subscribes to OrderFilled, loads open positions)
        await position_tracker.start()

        # Start strategy engine (subscribes to BarCompleted, QuoteReceived)
        await strategy_engine.start()

        logger.info("strategy_engine_initialized")

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

    except Exception as e:
        import os

        from rich.console import Console
        from rich.panel import Panel

        console = Console(stderr=True)
        console.print(
            Panel(
                f"[bold red]{type(e).__name__}[/]: {e}",
                title="Startup Failed",
                border_style="red",
            )
        )
        console.print("\n[dim]Your code:[/]")
        console.print("  → [cyan]src/main.py:24[/] in lifespan")
        console.print("  → [cyan]src/common/database/connection.py:32[/] in connect")
        os._exit(1)

    logger.info("application_started")
    yield
    logger.info("application_stopping")

    # Graceful shutdown
    await strategy_engine.stop()

    if settings.enable_jobs:
        JobScheduler.shutdown(wait=True)

    await Cache.disconnect()
    await Database.disconnect()

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

    health_coordinator = HealthCoordinator(timeout=5.0)
    health_coordinator.register("database", check_database)
    health_coordinator.register("redis", check_redis)

    @app.get("/health")
    async def health_check() -> dict:
        result = await health_coordinator.check_all()
        result["version"] = settings.app_version
        result["environment"] = settings.environment
        return result

    @app.get(f"{settings.api_prefix}/system/jobs")
    async def list_jobs() -> list[dict]:
        return JobScheduler.get_jobs()

    app.include_router(market_data_router, prefix=settings.api_prefix)
    app.include_router(quote_router, prefix=settings.api_prefix)
    app.include_router(strategy_router, prefix=settings.api_prefix)
    app.include_router(trading_router, prefix=settings.api_prefix)
    app.include_router(backtest_router, prefix=settings.api_prefix)

    return app


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
