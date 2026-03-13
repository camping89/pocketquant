# Phase 2: Rewrite Lifespan with Explicit Init/Shutdown

**Priority:** High | **Status:** Pending | **Effort:** M

## Overview

Replace `container.init_resources()` / `container.shutdown_resources()` with explicit constructor calls in the lifespan context manager. Build the `Services` dataclass and store on `app.state.services`.

## Context Links

- Current lifespan: `src/main.py:21-50`
- Resource init functions: `src/container.py:93-157`
- App factory: `src/main.py:53-75`

## Key Insight

The 6 current Resource providers are just async init functions with yield. We replace them with explicit calls — same logic, no library indirection.

## Implementation Steps

1. Rewrite `lifespan()` in `src/main.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    logger.info("application_starting", environment=settings.environment)

    # --- Init in dependency order (same as current) ---
    # 1. Persistence
    database = Database()
    await database.connect(settings)
    cache = Cache()
    await cache.connect(settings)

    # 2. Repositories (stateless, just need database ref)
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
    quote_service = QuoteService(settings=settings, cache=cache, bar_manager=bar_manager)

    # 6. Application services (async init — same as Resource providers)
    order_manager = OrderManager(event_bus, order_repo)
    await order_manager.load_pending_orders()

    position_tracker = PositionTracker(event_bus, position_repo)
    await position_tracker.start()

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
    await strategy_engine.start()

    # 7. Build registry
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

    # Store on app.state
    app.state.services = services
    # Hot-path for middleware (same as current)
    app.state.cache = cache
    app.state.database = database

    try:
        # Post-init tasks
        await ensure_all_indexes(services)
        await register_all_handlers(services)
        await start_background_jobs(services)

        logger.info("application_started")
        yield
    except Exception as e:
        handle_startup_failure(e)
    finally:
        # Shutdown in reverse order
        logger.info("application_stopping")
        await strategy_engine.stop()
        # position_tracker and order_manager have no explicit shutdown
        if settings.enable_jobs:
            job_scheduler.shutdown(wait=True)
        await cache.disconnect()
        await database.disconnect()
        logger.info("application_stopped")
```

2. Update `create_app()` — remove container creation:

```python
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
    register_routes(app, settings)  # no container param needed

    return app
```

## Common Pitfalls

- **Exception handling in lifespan**: current code catches startup errors and calls `shutdown_resources()`. New code uses try/finally to ensure shutdown always runs.
- **Startup failure**: if `database.connect()` fails, only disconnect what was already connected. The `finally` block handles this because Python skips lines after the failure.
- **`app.state.container` removal**: any code reading `app.state.container` must switch to `app.state.services`

## Todo

- [ ] Rewrite `lifespan()` in `src/main.py`
- [ ] Rewrite `create_app()` — remove container
- [ ] Handle startup failure ordering (only shutdown what was initialized)
- [ ] Remove `app.state.container` references
- [ ] Verify shutdown order matches current reverse order

## Success Criteria

- App starts and shuts down cleanly
- Same init order: database → cache → scheduler → order_manager → position_tracker → strategy_engine
- Same shutdown order: strategy_engine → scheduler → cache → database
- No `dependency-injector` imports in `main.py`
