"""PocketQuant application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.common.logging import get_logger, setup_logging
from src.config import get_settings
from src.main_extensions import (
    configure_middleware,
    handle_startup_failure,
    register_routes,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    logger.info("application_starting", environment=settings.environment)

    # Import here to keep module-level imports lightweight
    from src.application.market_data.bar_manager import BarManager
    from src.application.market_data.quote_service import QuoteService
    from src.application.strategy.strategy_engine import StrategyEngine
    from src.application.trading.order_manager import OrderManager
    from src.application.trading.position_tracker import PositionTracker
    from src.common.health import HealthCoordinator
    from src.common.mediator.mediator import Mediator
    from src.common.messaging import EventBus
    from src.features.risk.check_risk.handler import RiskCheckHandler
    from src.handler_registration import register_all_handlers
    from src.infrastructure.brokers import BrokerFactory
    from src.infrastructure.scheduling.scheduler import JobScheduler
    from src.infrastructure.tradingview import TradingViewProvider
    from src.main_extensions import (
        ensure_all_indexes,
        register_health_checks,
        start_background_jobs,
    )
    from src.persistence.mongodb import Database
    from src.persistence.redis import Cache
    from src.persistence.repositories.backtest_repository import BacktestRepository
    from src.persistence.repositories.ohlcv_repository import OHLCVRepository
    from src.persistence.repositories.optimization_repository import (
        OptimizationRepository,
    )
    from src.persistence.repositories.order_repository import OrderRepository
    from src.persistence.repositories.position_repository import PositionRepository
    from src.persistence.repositories.symbol_repository import SymbolRepository
    from src.persistence.repositories.sync_status_repository import (
        SyncStatusRepository,
    )
    from src.services import Services

    # --- Init in dependency order ---
    # Track what's been initialized for safe shutdown
    database = Database()
    cache = Cache()
    strategy_engine = None
    job_scheduler = None

    # 1. Persistence
    await database.connect(settings)
    try:
        await cache.connect(settings)
        # 2. Repositories
        order_repo = OrderRepository(database=database)
        position_repo = PositionRepository(database=database)
        backtest_repo = BacktestRepository(database=database)
        ohlcv_repo = OHLCVRepository(database=database)
        symbol_repo = SymbolRepository(database=database)
        sync_status_repo = SyncStatusRepository(database=database)
        optimization_repo = OptimizationRepository(database=database)

        # 3. Core messaging
        event_bus = EventBus(max_history=100)
        mediator = Mediator()

        # 4. Infrastructure
        job_scheduler = JobScheduler()
        if settings.enable_jobs:
            job_scheduler.initialize(settings)
            job_scheduler.start()

        tv_provider = TradingViewProvider(settings=settings)
        broker_factory = BrokerFactory()
        risk_handler = RiskCheckHandler()
        health_coordinator = HealthCoordinator(timeout=5.0)

        # 5. Market data services
        bar_manager = BarManager(cache=cache, ohlcv_repository=ohlcv_repo)
        quote_service = QuoteService(
            settings=settings, cache=cache, bar_manager=bar_manager
        )

        # 6. Application services (async init)
        order_manager = OrderManager(event_bus, order_repo)
        await order_manager.load_pending_orders()

        position_tracker = PositionTracker(event_bus, position_repo)
        await position_tracker.start()

        strategy_engine = StrategyEngine(
            event_bus=event_bus,
            broker_factory=broker_factory,
            order_manager=order_manager,
            position_tracker=position_tracker,
            risk_handler=risk_handler,
            default_broker_config={
                "initial_balance": settings.paper_initial_balance,
                "slippage_percent": settings.paper_slippage_percent,
                "api_key": settings.okx_api_key,
                "api_secret": settings.okx_api_secret,
                "passphrase": settings.okx_passphrase,
                "demo": settings.okx_demo_mode,
            },
        )
        await strategy_engine.start()

        # 7. Build registry and store on app.state
        services = Services(
            settings=settings,
            database=database,
            cache=cache,
            order_repository=order_repo,
            position_repository=position_repo,
            backtest_repository=backtest_repo,
            ohlcv_repository=ohlcv_repo,
            symbol_repository=symbol_repo,
            sync_status_repository=sync_status_repo,
            optimization_repository=optimization_repo,
            event_bus=event_bus,
            mediator=mediator,
            job_scheduler=job_scheduler,
            tv_provider=tv_provider,
            broker_factory=broker_factory,
            risk_handler=risk_handler,
            health_coordinator=health_coordinator,
            bar_manager=bar_manager,
            quote_service=quote_service,
            order_manager=order_manager,
            position_tracker=position_tracker,
            strategy_engine=strategy_engine,
        )

        app.state.services = services
        # Hot-path for middleware (same as before)
        app.state.cache = cache
        app.state.database = database

        # Post-init tasks
        await ensure_all_indexes(services)
        register_all_handlers(services)
        register_health_checks(services, app)
        await start_background_jobs(services)

        logger.info("application_started")
        yield
    except Exception as e:
        handle_startup_failure(e)
    finally:
        # Shutdown in reverse order — only stop what was initialized
        logger.info("application_stopping")
        if strategy_engine is not None:
            await strategy_engine.stop()
        if job_scheduler is not None and settings.enable_jobs:
            job_scheduler.shutdown(wait=True)
        await cache.disconnect()
        await database.disconnect()
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

    configure_middleware(app, settings)
    register_routes(app, settings)

    return app


app = create_app()
