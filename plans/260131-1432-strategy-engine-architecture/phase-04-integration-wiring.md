# Phase 4: Integration & Wiring

## Context Links

- **Parent Plan:** [plan.md](./plan.md)
- **Dependencies:** [Phase 1](./phase-01-domain-layer-models.md), [Phase 2](./phase-02-infrastructure-brokers.md), [Phase 3](./phase-03-feature-strategy-trading.md)
- **Blocked By:** Phase 3 (all features complete)
- **Research:** [Strategy Patterns](./research/researcher-02-strategy-engine-patterns.md)

## Overview

| Field | Value |
|-------|-------|
| Date | 2026-01-31 |
| Priority | P1 |
| Status | pending |
| Effort | 2h |

Wire all components together: register handlers in main.py, subscribe StrategyEngine to EventBus, add OKX settings to config, create example strategy YAML, update documentation.

## Key Insights

1. **Lifespan initialization order** - Brokers after DB/Cache, StrategyEngine after brokers
2. **EventBus subscriptions** - StrategyEngine subscribes to existing BarCompleted/QuoteReceived
3. **Config extension** - Add OKX credentials, strategy directory path
4. **Example strategy** - Simple MA crossover demonstrates full flow

## Requirements

### Functional
- StrategyEngine initialized in app lifespan
- EventBus subscriptions wired at startup
- CQRS handlers registered with Mediator
- API routes included in FastAPI app
- Example strategy YAML in strategies/ directory

### Non-Functional
- Graceful shutdown (stop strategies before broker disconnect)
- Configuration validation at startup
- Logging for all initialization steps

## Architecture

### Initialization Sequence

```
Lifespan Start
    │
    ├── 1. Database.connect()
    ├── 2. Cache.connect()
    ├── 3. JobScheduler.initialize()
    │
    ├── 4. Create shared instances:
    │       ├── Mediator
    │       ├── EventBus
    │       ├── BrokerFactory
    │       ├── OrderManager(event_bus)
    │       └── PositionTracker(event_bus)
    │
    ├── 5. Create StrategyEngine(
    │           event_bus, broker_factory,
    │           order_manager, position_tracker
    │       )
    │
    ├── 6. Register CQRS handlers
    │       ├── Strategy handlers
    │       ├── Trading handlers
    │       └── Risk handlers
    │
    ├── 7. StrategyEngine.start()
    │       └── Subscribes to BarCompleted, QuoteReceived
    │
    └── 8. Load strategies from YAML (optional auto-start)

    yield  ◄── Serve requests

Lifespan Stop
    │
    ├── 1. StrategyEngine.stop()
    │       └── Unsubscribe, close positions (optional)
    │
    ├── 2. JobScheduler.shutdown()
    ├── 3. Cache.disconnect()
    └── 4. Database.disconnect()
```

### Component Wiring Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  app.state.mediator ──────────┬──────────────────────────────┐  │
│  app.state.event_bus ─────────┼────────────────────────────┐ │  │
│  app.state.strategy_engine ───┼──────────────────────────┐ │ │  │
│                               │                          │ │ │  │
│  ┌────────────────────────────▼────────────────────────┐ │ │ │  │
│  │                    Mediator                          │ │ │ │  │
│  │  ├── LoadStrategyCommand → LoadStrategyHandler      │ │ │ │  │
│  │  ├── StartStrategyCommand → StartStrategyHandler    │ │ │ │  │
│  │  ├── SubmitOrderCommand → SubmitOrderHandler        │ │ │ │  │
│  │  ├── GetPositionsQuery → GetPositionsHandler        │ │ │ │  │
│  │  └── ...                                            │ │ │ │  │
│  └─────────────────────────────────────────────────────┘ │ │ │  │
│                                                          │ │ │  │
│  ┌───────────────────────────────────────────────────────▼─┼─┤  │
│  │                     EventBus                            │ │  │
│  │  Subscribers:                                           │ │  │
│  │  ├── BarCompleted → StrategyEngine._on_bar_completed ◄──┘ │  │
│  │  ├── QuoteReceived → StrategyEngine._on_quote_received    │  │
│  │  ├── OrderFilled → PositionTracker._on_order_filled       │  │
│  │  └── ...                                                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  app.include_router(strategy_router)                            │
│  app.include_router(trading_router)                             │
└─────────────────────────────────────────────────────────────────┘
```

## Related Code Files

### Files to Create

```
strategies/
├── examples/
│   └── ma-crossover-btc-usdt.yaml    # Example strategy config

tests/
├── integration/
│   └── test_strategy_engine_integration.py
```

### Files to Modify

```
src/main.py                    # Add strategy engine initialization
src/config.py                  # Add OKX + strategy settings
.env.example                   # Add new env vars
pyproject.toml                 # Add pyyaml dependency (if not present)
docs/system-architecture.md   # Document new components
README.md                      # Add strategy engine section
```

## Implementation Steps

### Step 1: Update Config (15 min)

1. Update `src/config.py`:
   ```python
   class Settings(BaseSettings):
       # ... existing fields ...

       # OKX Broker
       okx_api_key: str | None = None
       okx_api_secret: str | None = None
       okx_passphrase: str | None = None
       okx_demo_mode: bool = True

       # Strategy Engine
       strategies_dir: str = "strategies"
       auto_load_strategies: bool = False
       default_broker: str = "paper"
       paper_initial_balance: float = 100_000.0
       paper_slippage_percent: float = 0.001
   ```

2. Update `.env.example`:
   ```env
   # OKX Broker (optional, for live trading)
   OKX_API_KEY=
   OKX_API_SECRET=
   OKX_PASSPHRASE=
   OKX_DEMO_MODE=true

   # Strategy Engine
   STRATEGIES_DIR=strategies
   AUTO_LOAD_STRATEGIES=false
   DEFAULT_BROKER=paper
   PAPER_INITIAL_BALANCE=100000
   PAPER_SLIPPAGE_PERCENT=0.001
   ```

### Step 2: Update main.py Lifespan (45 min)

1. Add imports:
   ```python
   from src.features.strategy import (
       StrategyEngine,
       StrategyLoader,
       LoadStrategyCommand,
       LoadStrategyHandler,
       StartStrategyCommand,
       StartStrategyHandler,
       GetStrategiesQuery,
       GetStrategiesHandler,
       strategy_router,
   )
   from src.features.trading import (
       OrderManager,
       PositionTracker,
       SubmitOrderCommand,
       SubmitOrderHandler,
       GetOrdersQuery,
       GetOrdersHandler,
       GetPositionsQuery,
       GetPositionsHandler,
       trading_router,
   )
   from src.features.risk import RiskCheckHandler
   from src.infrastructure.brokers import BrokerFactory
   ```

2. Update lifespan function:
   ```python
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

           if settings.enable_jobs:
               JobScheduler.initialize(settings)
               JobScheduler.start()
               register_sync_jobs()

           # Existing handlers...
           tv_provider = TradingViewProvider(settings)
           # ... existing registrations ...

           # === NEW: Strategy Engine Setup ===
           broker_factory = BrokerFactory()
           order_manager = OrderManager(event_bus)
           position_tracker = PositionTracker(event_bus)
           risk_handler = RiskCheckHandler()

           strategy_engine = StrategyEngine(
               event_bus=event_bus,
               broker_factory=broker_factory,
               order_manager=order_manager,
               position_tracker=position_tracker,
               risk_handler=risk_handler,
               settings=settings
           )

           app.state.strategy_engine = strategy_engine
           app.state.order_manager = order_manager
           app.state.position_tracker = position_tracker

           # Register strategy handlers
           mediator.register(LoadStrategyCommand, LoadStrategyHandler(strategy_engine))
           mediator.register(StartStrategyCommand, StartStrategyHandler(strategy_engine))
           mediator.register(GetStrategiesQuery, GetStrategiesHandler(strategy_engine))

           # Register trading handlers
           mediator.register(SubmitOrderCommand, SubmitOrderHandler(order_manager))
           mediator.register(GetOrdersQuery, GetOrdersHandler(order_manager))
           mediator.register(GetPositionsQuery, GetPositionsHandler(position_tracker))

           # Start position tracker (subscribes to OrderFilled)
           await position_tracker.start()

           # Start strategy engine (subscribes to BarCompleted, QuoteReceived)
           await strategy_engine.start()

           # Auto-load strategies if configured
           if settings.auto_load_strategies:
               strategies_path = Path(settings.strategies_dir)
               if strategies_path.exists():
                   configs = StrategyLoader.load_all(strategies_path)
                   for config in configs:
                       await strategy_engine.load_strategy(config)
                   logger.info("strategies_loaded", count=len(configs))

           set_mediator(mediator)

       except Exception as e:
           # ... existing error handling ...

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
   ```

3. Include new routers:
   ```python
   app.include_router(strategy_router, prefix=settings.api_prefix)
   app.include_router(trading_router, prefix=settings.api_prefix)
   ```

### Step 3: Create Example Strategy YAML (15 min)

1. Create `strategies/examples/ma-crossover-btc-usdt.yaml`:
   ```yaml
   # Moving Average Crossover Strategy
   # Long when fast MA crosses above slow MA
   # Exit when fast MA crosses below slow MA

   id: ma-cross-btc-5m
   name: "MA Crossover BTC/USDT"
   symbol: BTCUSDT
   exchange: OKX
   interval: 5m
   trigger: bar

   broker: paper  # Use 'okx' for live trading

   parameters:
     fast_period: 10
     slow_period: 20
     use_ema: true

   risk:
     model: percent_risk
     risk_per_trade: 0.01      # 1% per trade
     max_positions: 1
     max_exposure_percent: 0.1 # 10% max

   orders:
     entry_type: market
     take_profit:
       enabled: true
       distance_percent: 0.02  # 2% TP
     stop_loss:
       enabled: true
       distance_percent: 0.01  # 1% SL
   ```

### Step 4: Add PyYAML Dependency (5 min)

1. Check if pyyaml is in dependencies:
   ```bash
   grep pyyaml pyproject.toml
   ```
2. If not present, add to `pyproject.toml`:
   ```toml
   [project.dependencies]
   pyyaml = ">=6.0"
   ```
3. Run `uv sync`

### Step 5: Update Documentation (30 min)

1. Update `docs/system-architecture.md`:
   - Add Strategy Engine section
   - Document event flow
   - Add component diagram

2. Update `README.md`:
   - Add Strategy Engine feature
   - Add configuration section
   - Add example usage

### Step 6: Create Integration Test (15 min)

1. Create `tests/integration/test_strategy_engine_integration.py`:
   ```python
   import pytest
   from pathlib import Path

   from src.features.strategy import StrategyEngine, StrategyLoader
   from src.features.trading import OrderManager, PositionTracker
   from src.infrastructure.brokers import BrokerFactory
   from src.common.messaging import EventBus
   from src.domain.ohlcv.events import BarCompleted

   @pytest.fixture
   def strategy_engine():
       event_bus = EventBus()
       broker_factory = BrokerFactory()
       order_manager = OrderManager(event_bus)
       position_tracker = PositionTracker(event_bus)

       engine = StrategyEngine(
           event_bus=event_bus,
           broker_factory=broker_factory,
           order_manager=order_manager,
           position_tracker=position_tracker
       )
       return engine

   @pytest.mark.asyncio
   async def test_strategy_loads_from_yaml(strategy_engine):
       config = StrategyLoader.load(
           Path("strategies/examples/ma-crossover-btc-usdt.yaml")
       )
       await strategy_engine.load_strategy(config)
       assert len(strategy_engine.get_strategies()) == 1

   @pytest.mark.asyncio
   async def test_bar_event_triggers_strategy(strategy_engine):
       # Load and start strategy
       config = StrategyLoader.load(...)
       await strategy_engine.load_strategy(config)
       await strategy_engine.start()

       # Simulate bar event
       event = BarCompleted(
           symbol="BTCUSDT",
           exchange="OKX",
           interval="5m",
           open=50000.0,
           high=50100.0,
           low=49900.0,
           close=50050.0,
           volume=100.0
       )
       await strategy_engine._on_bar_completed(event)

       # Verify strategy processed
       # (specific assertions depend on strategy logic)
   ```

## Todo List

- [ ] Update config.py with OKX and strategy settings
- [ ] Update .env.example with new variables
- [ ] Update main.py lifespan with strategy engine init
- [ ] Register strategy CQRS handlers in main.py
- [ ] Register trading CQRS handlers in main.py
- [ ] Include strategy and trading routers
- [ ] Create strategies/ directory structure
- [ ] Create example MA crossover YAML
- [ ] Add pyyaml dependency if missing
- [ ] Update system-architecture.md
- [ ] Update README.md with strategy section
- [ ] Create integration test
- [ ] Run full test suite
- [ ] Manual test: load strategy via API

## Success Criteria

1. Application starts without errors
2. Strategy engine logs subscription to EventBus
3. `/api/v1/strategies` returns empty list (no strategies loaded)
4. POST load strategy command succeeds
5. BarCompleted event triggers strategy.on_bar()
6. Orders appear in `/api/v1/orders` after signal
7. Positions appear in `/api/v1/positions` after fill

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Circular imports | Medium | Medium | Careful import ordering |
| Missing dependency | Low | Low | Test in clean env |
| Config validation fail | Low | Medium | Provide sensible defaults |
| Event subscription order | Medium | High | Document init sequence |

## Security Considerations

- **OKX credentials optional** - App works without them (paper only)
- **Demo mode default** - okx_demo_mode=True prevents accidental live trades
- **No secrets in example YAML** - Only strategy parameters

## Next Steps

After Phase 4 completion:
1. Full system test with paper broker
2. Create additional strategy examples
3. Implement backtest mode (Phase 5, future)
4. Add performance metrics collection
