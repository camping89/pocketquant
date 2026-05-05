# System Architecture

**Last Updated:** 2026-04-13 | **Version:** 3.5 | **Status:** Production Ready | **Pattern:** DDD + CQRS + Clean Architecture + Dishka | **Structure:** 4 backend packages + 1 frontend package | **Codebase:** 334 files, ~16,815 LOC

Current note: for local run/test steps and canonical route names, use [README](../README.md) and [run-and-test-guide](./run-and-test-guide.md). This document remains a deeper design reference.

## High-Level Architecture

PocketQuant uses **Clean Architecture + DDD + CQRS** with strict unidirectional dependency flow: Features → Application → Domain, Infrastructure → Domain. A modern React 19 SPA frontend consumes the REST API.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Client Layer (Browser)                       │
│  pocketquant-web: React 19 + Vite + Lightweight Charts         │
│  Candlestick chart, 5 indicators, symbol/interval selectors     │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTP/REST (proxy to :41920)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                         External Services                        │
│     TradingView (REST + WS)  │  OKX (REST + WS)  │  Scheduler   │
└───────────┬─────────────────────────┬───────────────────────────┘
            │                         │
            ▼                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              Features Layer (CQRS Operation Routers)             │
│  Commands/Queries → Handlers → Domain + Infrastructure          │
│  backtesting/ | market_data/ | strategy/ | trading/ | risk/     │
└────────────────────────┬────────────────────────────────────────┘
                         │
            ┌────────────┴────────────┐
            │                         │
            ▼                         ▼
┌──────────────────────────┐   ┌──────────────────────────┐
│  Application Layer       │   │   Domain Layer           │
│  (Orchestrators)         │◄──┤   (Pure Logic)           │
│  ├─ StrategyAppService       │   │   ├─ Aggregates         │
│  ├─ BacktestAppService       │   │   ├─ Value Objects      │
│  ├─ BarAppService           │   │   ├─ Domain Events      │
│  ├─ OrderAppService         │   │   ├─ Interfaces         │
│  └─ PositionAppService      │   │   └─ Domain Services    │
└──────────┬───────────────┘   └──────────────────────────┘
           │                            │
           │    ┌───────────────────────┘
           │    │
           ▼    ▼
┌─────────────────────────────────────────────────────────────────┐
│              Infrastructure Layer (External I/O)                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ Brokers  │  │Providers │  │Persistence│  │ Scheduling  │   │
│  │ (OKX,   │  │(TradingVw│  │(MongoDB,  │  │  (APScheduler)  │
│  │ Paper)  │  │ WebSocket│  │ Redis)    │  │              │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
        │              │               │            │
        ▼              ▼               ▼            ▼
    ┌────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────┐
    │  OKX   │  │TradingVw │  │  MongoDB     │  │ Redis /  │
    │ Live   │  │ Market   │  │  (Bars,     │  │BackgroundJobs
    │Trading │  │  Data    │  │  Orders,    │  │          │
    │        │  │          │  │  Positions) │  │          │
    └────────┘  └──────────┘  └──────────────┘  └──────────┘
```

**Dependency Direction:** Features ← Application ← Domain, Infrastructure ← Domain (no reverse dependencies)

## Clean Architecture Layer Breakdown

### Layer 1: Domain (Pure Business Logic) — packages/pocketquant-core/src/pocketquant/core/domain/

**Purpose:** Core business rules with ZERO external dependencies. Reusable domain concepts.

**Rules:**
- No I/O imports (no pymongo, redis, aiohttp, http)
- Immutable value objects (frozen dataclasses, enums)
- Domain events for state changes (HistoricalDataSyncedEvent, OrderFilledEvent, etc.)
- Validation via __post_init__
- Enforced via `test_domain_purity.py` (AST check)

**Structure:**
```
domain/
├── backtest/               # Backtesting domain
│   └── services/performance_calculator.py
├── bar/                    # TOP-LEVEL: Market bars (renamed from ohlcv/)
│   ├── entities.py         # Bar entity with to_mongo/from_mongo
│   ├── events.py           # BarCompletedEvent, HistoricalDataSyncedEvent
│   ├── value_objects.py    # OHLCV, BarRange
│   └── services/bar_builder.py  # BarBuilder service
├── order/                  # TOP-LEVEL: Order lifecycle
│   ├── entities.py         # OrderAggregate with to_mongo/from_mongo
│   ├── enums.py            # OrderType, OrderSide, OrderStatus
│   └── events.py           # Order events
├── position/               # TOP-LEVEL: Position tracking
│   ├── entities.py         # PositionAggregate with to_mongo/from_mongo
│   ├── enums.py            # PositionSide
│   ├── events.py           # Position events
│   └── value_objects.py    # PnL
├── symbol/                 # TOP-LEVEL: Tradeable instruments
│   └── entities.py         # Symbol (flattened from SymbolAggregate)
├── sync_status/            # TOP-LEVEL: Sync tracking
│   └── entities.py         # SyncStatus
├── backtest/               # TOP-LEVEL: Backtest results
│   ├── entities.py         # BacktestResult, OptimizationResult
│   ├── value_objects.py    # TradeRecord, EquityPoint, BacktestMetrics
│   └── services/performance_calculator.py  # NumPy metrics
├── concepts/               # NON-PERSISTED logic
│   ├── quote/
│   │   ├── events.py       # QuoteReceivedEvent, QuoteUpdatedEvent
│   │   └── value_objects.py  # Price, QuoteTick
│   ├── risk/
│   │   ├── enums.py        # RiskModel enum
│   │   ├── value_objects.py  # RiskConfig
│   │   └── services/position_sizer.py  # PositionSizer (pure calc)
│   └── strategy/
│       ├── enums.py        # Direction enum
│       ├── events.py       # SignalGeneratedEvent
│       ├── interfaces.py   # IStrategy ABC
│       ├── value_objects.py  # Signal, StrategyConfig, OrderConfig, StopLossConfig, TakeProfitConfig
│       └── services/ma_crossover.py  # MACrossoverStrategy
└── shared/                 # Cross-cutting
    ├── enums.py            # Interval enum
    ├── events.py           # DomainEvent base (was domain_event.py)
    └── value_objects.py    # INTERVAL_SECONDS mapping
```

**Example - Bar Entity with MongoDB Persistence:**
All domain entities use Pydantic BaseModel with built-in `to_mongo()` / `from_mongo()` for persistence.

**Example - Symbol Entity (Flattened from SymbolAggregate):**
Symbol is now a simple flat entity with `code`, `exchange`, `name`, `asset_type`, `is_active` fields and standard `to_mongo()`/`from_mongo()` methods.

**Example - Domain Service (Pure Logic):**
BarBuilder and PositionSizer are pure domain services with zero I/O, implementing domain business rules.

### Layer 2: Application (Orchestrators) — packages/{backtest, trading}/src/pocketquant/

**Purpose:** Orchestrate domain logic + infrastructure I/O to fulfill business use cases. Stateful services and engines that coordinate between layers.

**Structure:**
```
application/
├── backtesting/              # Backtest orchestration
│   ├── backtest_app_service.py       # BacktestAppService (execute backtest)
│   ├── grid_optimization_app_service.py  # GridOptimizationAppService (parameter search)
│   ├── historical_replay_app_service.py  # HistoricalReplayAppService (inject bars)
│   ├── result_collector.py           # ResultCollector (collect fills, metrics)
│   └── models/                       # DTOs, performance calculator
├── market_data/              # Data sync orchestration
│   ├── bar_app_service.py          # BarAppService (multi-interval aggregation)
│   ├── quote_app_service.py        # QuoteAppService (WebSocket lifecycle)
│   └── models/                     # DTOs for market data
├── strategy/                 # Strategy orchestration
│   └── strategy_app_service.py     # StrategyAppService (dispatch, signal handling)
├── trading/                  # Trading orchestration
│   ├── order_app_service.py        # OrderAppService (order state, recovery)
│   └── position_app_service.py     # PositionAppService (position tracking, P&L)
└── __init__.py
```

**Example - Application Service:**
```python
# StrategyAppService - orchestrates domain + infrastructure
class StrategyAppService:
    def __init__(self, broker: IBroker, event_bus: EventBus):
        self.broker = broker
        self.event_bus = event_bus
        self.strategy: Optional[IStrategy] = None

    async def on_bar(self, bar: Bar) -> None:
        """Called when bar completes."""
        # 1. Domain: Get strategy signal
        signal = await self.strategy.on_bar(bar)

        # 2. Infrastructure: Check risk
        approved = await risk_check(signal)

        # 3. Infrastructure: Execute via broker
        if approved:
            order = await self.broker.submit_order(approved.order)

        # 4. Infrastructure: Publish event
        await self.event_bus.publish(SignalGeneratedEvent(...))
```

### Layer 3: Features (CQRS Operation Routes) — packages/pocketquant-api/src/pocketquant/api/features/

**Purpose:** Thin HTTP routing layer. Routes receive requests, delegate to handlers, return responses.

**Pattern:** Operation-first vertical slices. Each operation is a self-contained use case (command/query + handler).

**Structure:**
```
features/
├── backtesting/              # Backtest feature (5 operations)
│   ├── run/                 # Operation: Execute backtest
│   │   ├── command.py       # RunBacktestCommand
│   │   ├── handler.py       # RunBacktestHandler → BacktestAppService.run()
│   │   └── route.py         # POST /api/v1/backtest/run
│   ├── optimize/            # Operation: Optimize parameters
│   │   ├── command.py       # OptimizeCommand
│   │   ├── handler.py       # OptimizeHandler → GridOptimizationAppService.optimize()
│   │   └── route.py         # POST /api/v1/backtest/optimize
│   ├── get_result/          # Operation: Get backtest result
│   │   ├── query.py
│   │   └── handler.py
│   ├── list_results/        # Operation: List results
│   │   ├── query.py
│   │   └── handler.py
│   ├── get_optimization/    # Operation: Get optimization result
│   │   ├── query.py
│   │   └── handler.py
│   └── router.py            # Feature router (aggregates all operations)
├── market_data/              # Market data feature
│   ├── sync/                # Nested group
│   │   ├── sync_one/       # Operation: Sync single symbol
│   │   ├── sync_bulk/      # Operation: Sync multiple symbols
│   │   └── router.py
│   ├── bar/                 # Nested group (renamed from ohlcv/)
│   │   ├── get_bars/       # Operation: Get bars
│   │   └── router.py
│   ├── integrity/           # NEW: Nested group for data integrity
│   │   ├── check/          # Operation: Check bar alignment + gaps
│   │   ├── repair/         # Operation: Delete misaligned, resync gaps
│   │   └── route.py
│   ├── quotes/              # Nested group
│   │   ├── start_feed/     # Operation: Start WebSocket
│   │   ├── stop_feed/      # Operation: Stop WebSocket
│   │   ├── subscribe/      # Operation: Subscribe
│   │   ├── get_all/        # Operation: Get all quotes
│   │   └── router.py
│   ├── status/              # Nested group
│   │   ├── get_sync_status/
│   │   └── router.py
│   ├── list_symbols/        # Operation: List symbols
│   └── router.py
├── strategy/                 # Strategy feature (10 operations)
│   ├── get_all/            # Operation: List strategies
│   ├── get_one/            # Operation: Get strategy
│   ├── load/               # Operation: Load strategy YAML
│   ├── start/              # Operation: Start strategy
│   ├── stop/               # Operation: Stop strategy
│   ├── subscriptions/       # NEW: Nested group for strategy subscriptions
│   │   ├── add_symbol/     # Operation: POST /strategies/{strategy_id}/symbols
│   │   ├── list_symbols/   # Operation: GET /strategies/{strategy_id}/symbols
│   │   ├── delete_symbol/  # Operation: DELETE /strategies/{strategy_id}/symbols/{sub_id}
│   │   ├── run_all_backtest/ # Operation: POST /strategies/{strategy_id}/backtest/run-all
│   │   ├── get_subscription_backtest/ # Operation: GET /strategies/{strategy_id}/symbols/{sub_id}/backtest
│   │   └── router.py
│   ├── delete/             # Operation: DELETE /strategies/{strategy_id} (cascade)
│   └── router.py
├── trading/                  # Trading feature (3 operations)
│   ├── list_orders/        # Operation: List orders
│   ├── get_order/          # Operation: Get order
│   ├── list_positions/     # Operation: List positions
│   ├── get_position/       # Operation: Get position
│   └── router.py
├── risk/                     # Risk feature (1 operation)
│   ├── check_risk/         # Operation: Pre-trade validation
│   └── router.py
└── __init__.py
```

**Operation Pattern (Inside each operation folder):**
```
operation_name/
├── command.py or query.py    # Request definition (Pydantic model)
├── handler.py                # CQRS handler (async handle method)
├── route.py                  # FastAPI route (optional, often in parent router)
└── __init__.py
```

**Handler 5-Step Pattern:**
1. Receive Command/Query → 2. Fetch Infrastructure → 3. Execute Domain → 4. Persist Infrastructure → 5. Return DTO

**Example:**
```python
@handles(RunBacktestCommand)
class RunBacktestHandler(Handler[RunBacktestCommand, BacktestResultDTO]):
    async def handle(self, cmd: RunBacktestCommand) -> BacktestResultDTO:
        # 1. Fetch strategy config from infrastructure
        strategy = await StrategyLoader.load_yaml(cmd.strategy_yaml)

        # 2. Fetch historical bars from infrastructure
        bars = await BarRepository.get_bars(cmd.symbol, cmd.start_date, cmd.end_date)

        # 3. Execute domain logic via BacktestAppService
        results = BacktestAppService.run(strategy, bars, self.broker)

        # 4. Persist to MongoDB
        await BacktestRepository.save(results)

        # 5. Return DTO (not domain entity)
        return BacktestResultDTO(
            run_id=results.id,
            sharpe_ratio=results.metrics.sharpe,
            ...
        )
```

### Layer 4: Infrastructure (External I/O) — packages/pocketquant-core/src/pocketquant/core/infrastructure/ + persistence/

**Purpose:** All external integrations: databases, brokers, data providers, scheduling, HTTP.

**Structure:**
```
infrastructure/                        # External I/O (brokers, providers, scheduling, webhooks)
├── brokers/                  # Order execution abstraction
│   ├── interface.py         # IBroker interface (submit, cancel, get positions)
│   ├── factory.py           # BrokerFactory (create paper or okx)
│   ├── models.py            # Execution models (ExecutionResult, etc.)
│   ├── paper/               # PaperBroker (in-memory simulation)
│   │   └── paper_broker.py
│   └── okx/                 # OKXBroker (live trading)
│       ├── okx_broker.py    # REST + WebSocket integration
│       ├── okx_mapper.py    # Domain ↔ OKX model mapping
│       └── websocket/       # OKX WebSocket protocol
│           ├── okx_websocket_client.py   # Low-level WebSocket
│           ├── okx_auth.py               # HMAC-SHA256 auth
│           ├── okx_message_parser.py     # JSON message parsing
│           ├── okx_order_mapper.py       # Order state mapping
│           ├── okx_position_mapper.py    # Position state mapping
│           └── okx_reconnection_handler.py  # Resilient connection
├── tradingview/              # TradingView integration
│   ├── provider.py          # TradingViewClient (REST via tvdatafeed)
│   └── websocket.py         # TradingViewWebSocketClient (binary frames)
├── http_client/              # Generic HTTP utilities
│   └── client.py            # Async HTTP client (aiohttp wrapper)
├── scheduling/               # Job scheduling (APScheduler)
└── webhooks/                 # Webhook delivery
    └── dispatcher.py        # WebhookDispatcher (HMAC signing, retry)

persistence/                           # Data access (MongoDB, Redis, repositories)
├── mongodb.py               # MongoDB async singleton (PyMongo)
├── redis.py                 # Redis async singleton (redis-py)
├── base_repository.py       # BaseRepository mixin (_collection() helper)
└── repositories/            # Data access layers (instance methods via DI)
    ├── bar_repository.py       # Bar persistence (renamed from ohlcv_repository.py)
    ├── order_repository.py     # Order persistence
    ├── position_repository.py  # Position tracking
    ├── backtest_repository.py  # Backtest results + subscription-scoped upsert
    ├── optimization_repository.py  # Parameter optimization
    ├── symbol_repository.py    # Symbol metadata
    ├── strategy_subscription_repository.py  # Strategy ↔ subscriptions (NEW)
    └── sync_status_repository.py   # Data sync status
# NOTE: schemas/ directory deleted (2026-03-15)
# Persistence logic consolidated into domain entities via to_mongo()/from_mongo()
```

**Key Services:**

| Service | Purpose |
|---------|---------|
| **MongoDBConnection** | Async collection access, pooling (5-50 connections) |
| **RedisConnection** | JSON serialization, pattern deletion, TTL support |
| **PaperBroker** | In-memory simulation, configurable slippage/delay |
| **OKXBroker** | Live trading, HMAC auth, exponential backoff reconnection |
| **TradingViewClient** | REST API via ThreadPoolExecutor (max 4 workers) |
| **TradingViewWebSocketClient** | Binary frame parsing (~m~{len}~m~{json}) |
| **JobScheduler** | APScheduler wrapper, async job execution, supports `second` param for cron offset (dodge bar-close race) |

### Layer 5: Common (Cross-Cutting) — packages/pocketquant-core/src/pocketquant/core/common/

**Purpose:** Shared utilities: CQRS mediator, event bus, middleware, tracing, health checks.

**Structure:**
```
common/
├── mediator/
│   ├── mediator.py           # Mediator (CQRS dispatcher)
│   ├── handler.py            # Handler[TRequest, TResponse] base + @handles decorator
│   ├── registry.py           # HandlerRegistry (auto-discovery)
│   └── exceptions.py         # HandlerNotFoundError, DuplicateHandlerError
├── messaging/
│   ├── event_bus.py          # EventBus (in-memory, FIFO, 50-event history)
│   ├── event_handler.py      # EventHandler base class
│   ├── event_registry.py     # @event_handler decorator + auto-discovery
│   └── ...
├── middleware/
│   ├── correlation_id.py     # CorrelationIdMiddleware (request tracking)
│   ├── request_logging.py    # RequestLoggingMiddleware
│   ├── idempotency.py        # IdempotencyMiddleware (24h TTL)
│   └── rate_limit.py         # RateLimitMiddleware (200 req/10s per IP)
├── tracing/
│   ├── correlation.py        # CorrelationID context management
│   └── context.py            # ContextVar storage
├── health/
│   ├── coordinator.py        # HealthCoordinator (parallel checks)
│   └── checks.py             # Database, cache, jobs health probes
├── database.py               # Database singleton (MongoDB)
├── cache.py                  # Cache singleton (Redis)
├── jobs.py                   # JobScheduler singleton (APScheduler)
├── uuid.py                   # UUID7 generation (time-ordered IDs)
├── logging.py                # Structured logging (structlog)
├── constants.py              # Cache keys, TTLs, limits, headers
└── __init__.py
```

**Key Components:**

| Component | Purpose |
|-----------|---------|
| **Mediator** | Route commands/queries to handlers, auto-discover via @handles |
| **EventBus** | Publish domain events, subscribe handlers via @event_handler |
| **CorrelationIdMiddleware** | Inject request ID for distributed tracing |
| **RateLimitMiddleware** | Token bucket per IP (200 req/10s) |
| **IdempotencyMiddleware** | Cache POST responses by idempotency_key header |
| **Database** | MongoDB async singleton |
| **Cache** | Redis async singleton |
| **JobScheduler** | APScheduler async wrapper |

### Layer 6: Presentation (Web UI) — packages/pocketquant-web/ (React SPA)

**Purpose:** TradingView-like charting interface for real-time market visualization and indicator analysis.

**Tech Stack:**
- **Vite 8** - Build tool with HMR
- **React 19** - UI framework with Hooks
- **TypeScript 5.9** - Type safety
- **Lightweight Charts 5.1** - High-performance candlestick rendering
- **TanStack Query 5.x** - Server state management, real-time polling

**Structure:**
```
src/
├── api/                  # REST client layer
│   ├── api-client.ts    # HTTP fetch wrapper (proxy to :41920)
│   └── market-data-api.ts  # Market data queries
├── components/
│   ├── chart/           # Charting components
│   │   ├── trading-chart.tsx  # Candlestick + volume + indicators
│   │   ├── use-chart.ts       # Lightweight Charts initialization
│   │   └── indicator-series.ts  # SMA, EMA, RSI, MACD, Bollinger
│   ├── controls/        # User controls
│   │   ├── symbol-selector.tsx   # Symbol dropdown
│   │   ├── interval-selector.tsx  # Timeframe picker (1m-1M)
│   │   └── indicator-toggles.tsx  # Show/hide indicators
│   └── layout/
│       └── app-header.tsx  # Navigation + branding
├── hooks/               # React custom hooks
│   ├── use-ohlcv.ts     # Fetch historical bars
│   ├── use-realtime-bar.ts  # Real-time polling (TanStack Query)
│   ├── use-symbols.ts   # Fetch symbol list
│   └── use-indicators.ts  # Indicator calculation
├── lib/
│   └── indicators/      # Pure indicator algorithms
│       ├── moving-average.ts  # SMA, EMA
│       ├── rsi.ts             # Relative Strength Index
│       ├── macd.ts            # MACD + signal line
│       └── bollinger-bands.ts # Upper, middle, lower bands
├── App.tsx              # Root component
└── main.tsx             # Vite entry point
```

**Key Features:**
- **Candlestick Chart:** Real-time OHLCV visualization via Lightweight Charts
- **Volume Overlay:** Trading volume as histogram below price
- **5 Indicators:** SMA (20/50), EMA (12/26), RSI (14), MACD (12,26,9), Bollinger Bands (20,2)
- **Symbol/Interval Selectors:** Switch data without page reload
- **Real-time Polling:** TanStack Query refetches bar data every 5-10s (configurable)
- **API Proxy:** Vite dev server proxies `/api/*` to `http://localhost:41920`

**Deployment:** Vite `dist/` served as static assets behind FastAPI (no separate server).

## Clean Architecture Request Flow

### Command Flow (State Mutation)

```
HTTP Request (POST /market-data/sync)
  ↓
Middleware Stack
  ├─ CorrelationIdMiddleware → inject correlation_id
  ├─ RateLimitMiddleware → check token bucket (200 req/10s)
  └─ IdempotencyMiddleware → return cached response if duplicate
  ↓
Route (features/market_data/sync/sync_one/route.py)
  ├─ Parse request body
  ├─ Build SyncSymbolCommand
  └─ Call Mediator.send(command)
  ↓
Mediator (common/mediator/mediator.py)
  ├─ Lookup handler via @handles(SyncSymbolCommand)
  └─ Call handler.handle(command)
  ↓
Handler (features/market_data/sync/sync_one/handler.py)
  ├─ [1] Fetch: TradingViewClient.fetch_ohlcv()  [infrastructure]
  ├─ [2] Validate: Bar.from_mongo()                [domain]
  ├─ [3] Persist: BarRepository.upsert_many()      [infrastructure]
  ├─ [4] Invalidate: Cache.delete_pattern()        [infrastructure]
  └─ [5] Publish: EventBus.publish(HistoricalDataSyncedEvent)
  ↓
Route Response
  └─ Return SyncResultDTO as JSON 200
```

**Handler 5-Step Pattern:**
1. **Fetch** from infrastructure (providers, repositories)
2. **Validate** via domain layer (aggregates, value objects)
3. **Persist** via infrastructure (database, cache writes)
4. **Invalidate** cache (pattern-based deletion)
5. **Publish** domain events (event subscribers react async)

### Query Flow (Read-Only)

```
HTTP Request (GET /market-data/bar/{exchange}/{symbol}?interval=1d&limit=100)
  ↓
Middleware Stack
  ├─ CorrelationIdMiddleware → inject correlation_id
  ├─ RateLimitMiddleware → check token bucket
  └─ (No idempotency for GET)
  ↓
Route (features/market_data/bar/get_bars/route.py)
  ├─ Parse query params
  ├─ Build GetBarsQuery
  └─ Call Mediator.send(query)
  ↓
Mediator (common/mediator/mediator.py)
  ├─ Lookup handler via @handles(GetBarsQuery)
  └─ Call handler.handle(query)
  ↓
Handler (features/market_data/bar/get_bars/handler.py)
  ├─ [1] Fetch: Cache.get(key) or BarRepository.get_bars()
  ├─ [2] Validate: Bar value objects
  ├─ [3] Cache: Cache.set(key, result, ttl=300)
  └─ [4] Return: BarsDTO (never return entities)
  ↓
Route Response
  └─ Return BarsDTO as JSON 200
```

## Trading Persistence Layer

### MongoDB Collections & Repository Access

**Collections (MongoDB, accessed via Repositories):**

| Collection | Repository | Purpose |
|-----------|-----------|---------|
| `bars` | BarRepository | Market OHLCV bars |
| `orders` | OrderRepository | Order lifecycle |
| `positions` | PositionRepository | Position tracking |
| `backtests` | BacktestRepository | Backtest results + subscription cache (dual-purpose via `subscription_id` field) |
| `optimizations` | OptimizationRepository | Parameter optimization |
| `symbols` | SymbolRepository | Symbol metadata |
| `sync_status` | SyncStatusRepository | Data sync progress |
| `strategy_subscriptions` | StrategySubscriptionRepository | Strategy ↔ (symbol/exchange/interval) subscriptions |
| `job_history` | JobHistoryRepository | Background job execution history |

**All repositories:**
- Inherit from `BaseRepository` (provides `_collection()` helper)
- Instance-based with `Database` injected via constructor
- Zero direct `Database.get_collection()` calls outside persistence layer
- Enforce schema validation via MongoDB document schemas

### Recovery on Startup

```
Application Startup
  ↓
OrderRepository.ensure_indexes() - Create MongoDB indexes
PositionRepository.ensure_indexes()
  ↓
OrderAppService.load_pending_orders()
  └─> Load orders with status: pending, submitted, partially_filled
      └─> Restore in-memory state + broker_order_id mapping
  ↓
PositionAppService.start()
  └─> PositionRepository.find_open()
      └─> Load all is_closed=false positions
      └─> Restore in-memory position state
  ↓
Ready to process market events and recover fills
```

### State Transitions

**Order Lifecycle:**
- **Submit:** OrderAggregate created → OrderRepository.save()
- **Fill:** OrderStatus = FILLED → OrderRepository.save() + publish OrderFilledEvent
- **Cancel:** OrderStatus = CANCELLED → OrderRepository.save()
- **Reject:** OrderStatus = REJECTED → OrderRepository.save()

**Position Lifecycle:**
- **Open:** First fill creates position → PositionRepository.save() + publish PositionOpenedEvent
- **Update:** Same-side fills increase quantity → PositionRepository.save()
- **Close:** Opposite-side fills reduce to zero → PositionRepository.save() + mark is_closed=true

## Broker Abstraction Layer

**IBroker Interface:** `submit_order()`, `cancel_order()`, `get_positions()`, `get_orders()`

| Broker | Type | Features |
|--------|------|----------|
| **PaperBroker** | Simulation | Slippage, fill delays, P&L calc, no dependencies |
| **OKXBroker** | Live | HMAC auth, exponential backoff reconnection, circuit breaker (10 failures → 5m pause) |

## Middleware Stack

**Order:** CorrelationId → RateLimit → Idempotency → Route Handler

| Middleware | Purpose |
|------------|---------|
| CorrelationId | Inject request ID for tracing |
| RateLimit | Token bucket: 200 req/10s per IP |
| Idempotency | Cache POST responses (24h TTL) |

## Event Bus Pattern

**Purpose:** Decouple features via domain events (in-memory, FIFO, 50 event max history).

**Characteristics:**
- Handlers publish → EventBus.publish(event) → subscribers notified sequentially
- Bounded history (**50 events max**, hardcoded in CoreProvider)
- Sync + async handlers supported
- No persistence (events lost on restart)

## Data Pipelines (Overview)

**See [handler-pipelines.md](./handler-pipelines.md) for detailed 27-handler flows.**

Key pipelines at high level:
1. **Historical Sync:** TradingView → BarRepository.upsert_many() → Cache invalidation → EventBus
2. **Real-time Quotes:** TradingView WebSocket → QuoteAppService → BarAppService (13 intervals) → MongoDB + EventBus
3. **Data Integrity:** Check alignment + gaps → Delete misaligned → Resync gaps (skip_filter=True) → Verify — Cron jobs @ 04:00 UTC (check) & every 12h (repair)
4. **Strategy Execution:** Market event → Strategy.on_bar() → Risk check → Broker.submit_order() → Position tracking
5. **Backtesting:** YAML config → Historical bars → PaperBroker.simulate_fills() → PerformanceCalculator → MongoDB
6. **Parameter Optimization:** GridOptimizationAppService → Parallel backtests → Best params → MongoDB

## Concurrency Model

- **Event Loop:** All async code on single event loop (FastAPI/Uvicorn)
- **Thread Pool:** TradingView REST (tvdatafeed) uses ThreadPoolExecutor (4 workers) to prevent blocking
- **Asyncio.Lock:** BarAppService uses lock for thread-safe OHLC atomic updates

## Dependency Injection (Dishka)

**dishka** library with 6 providers + auto-resolution via type hints. Dependencies resolved automatically by matching `__init__` parameter types.

**Key files:**
| File | Purpose |
|------|---------|
| `packages/pocketquant-api/src/pocketquant/api/di/container.py` | Factory: `create_container()`, handler registration |
| `packages/pocketquant-api/src/pocketquant/api/di/` | 6 Provider classes |
| `packages/pocketquant-api/src/pocketquant/api/main.py` | Lifespan: create container, setup_dishka |

**6 Providers:**
- **CoreProvider** - Settings, EventBus (max_history=**50**), Mediator
- **PersistenceProvider** - Database (PyMongo), Cache (Redis), 7 repositories
- **InfrastructureProvider** - Brokers (Paper, OKX), TradingViewClient, JobScheduler
- **MarketDataProvider** - BarAppService, QuoteAppService, 8 sync/integrity background jobs
- **TradingProvider** - OrderAppService, PositionAppService, StrategyAppService
- **HandlerProvider** - All 27 CQRS handlers (via @handles decorator)

**Handler Registration:** `register_handlers(container)` resolves all 27 handler types and registers with Mediator.

## Resource Lifecycle

### Startup Sequence

1. FastAPI lifespan async context manager started
2. Load settings from .env via pydantic-settings
3. Setup structured logging (structlog)
4. Create dishka AsyncContainer with 6 providers (initialization order: Core → Persistence → Infrastructure → MarketData → Trading → Handler)
5. `register_handlers(container)` resolves all 27 handlers, registers with Mediator
6. `ensure_all_indexes()` creates MongoDB indexes
7. `register_health_checks()` registers DB/Redis/job health probes
8. `start_background_jobs()` registers APScheduler sync jobs
9. `setup_dishka(container, app)` integrates dishka with FastAPI routes
10. Server ready on port 41920 (internal; host port via `APP_PORT` env var)

### Graceful Shutdown (container.close() in finally)

1. Stop accepting new requests
2. `container.close()` runs all provider cleanups in reverse order:
   - StrategyAppService.stop() — stop strategy engine
   - JobScheduler.shutdown(wait=True) — stop background jobs
   - Cache.disconnect() — close Redis
   - Database.disconnect() — close MongoDB

## Integration Points

| System | Type | Details |
|--------|------|---------|
| **TradingView** | HTTP + WS | ThreadPoolExecutor (4 workers), binary frames, exponential backoff |
| **OKX** | WS + Auth | HMAC-SHA256, 1s-30s backoff, 10-fail circuit breaker |
| **MongoDB** | Async | PyMongo, pool 5-50 connections, 8 collections |
| **Redis** | Async | redis-py, TTL: 60s quotes, 300s bars, 86400s idempotency |

## Error Handling

| Category | Strategy |
|----------|----------|
| **Transient** | Exponential backoff (0/3/8s, 15s budget in fetch_with_retry), auto-reconnect |
| **Permanent** | HTTP errors (4xx/5xx) |
| **Silent** | Log, continue execution |

**Data Sync Anomalies (Structured Logs):**
- `market_data.sync.fetch_recovered` (INFO) — Retry succeeded after attempt N
- `market_data.sync.no_progress` (WARN) — Zero bars inserted; tracked via no_progress_streak (broadened semantics: empty/misaligned/existing)
- `market_data.sync.stuck_threshold_crossed` (ERROR, once per streak) — Streak reaches 3× cadence threshold with stale last bar

## Performance & Security

**Characteristics:** Sync 1-5s per 5k bars | Quote <100ms | Bar aggregation <1ms/tick | Mediator <0.1ms | Quote throughput 1000+/sec

**Security:** Credentials via env vars only | Rate limit 200 req/10s per IP | Idempotency cache 24h TTL | MongoDB/Redis auth via DSN
