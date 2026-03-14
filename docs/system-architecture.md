# System Architecture

**Last Updated:** 2026-02-21 | **Version:** 3.1 | **Status:** Production Ready | **Pattern:** DDD + CQRS + Clean Architecture

## High-Level Architecture

PocketQuant uses **Clean Architecture + DDD + CQRS** with strict unidirectional dependency flow: Features → Application → Domain, Infrastructure → Domain.

```
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

### Layer 1: Domain (Pure Business Logic) — src/domain/

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
├── ohlcv/                  # Market data aggregates
│   ├── aggregate.py        # OHLCVAggregate (bar collection)
│   ├── entities.py         # Entities
│   ├── value_objects.py    # OHLCV, BarRange, immutable bar
│   ├── ohlcv_event.py      # HistoricalDataSyncedEvent, BarCompletedEvent
│   └── services/bar_builder.py  # BarBuilder service (incremental bar construction)
├── order/                  # Order lifecycle domain
│   ├── aggregate.py        # OrderAggregate
│   ├── value_objects.py    # Order, OrderStatus, OrderType, OrderSide enums
│   └── order_event.py      # OrderSubmittedEvent, OrderFilledEvent, etc.
├── position/               # Position tracking domain
│   ├── aggregate.py        # PositionAggregate
│   ├── value_objects.py    # Position, PositionSide, PnL
│   └── position_event.py   # PositionOpenedEvent, PositionClosedEvent
├── quote/                  # Real-time quote domain
│   ├── aggregate.py        # QuoteAggregate
│   ├── value_objects.py    # QuoteTick (price, volume, timestamp)
│   └── quote_event.py      # QuoteReceivedEvent
├── risk/                   # Risk management domain
│   ├── aggregate.py        # RiskConfigAggregate
│   ├── value_objects.py    # RiskConfig, RiskModel enum
│   └── services/position_sizer.py  # Position sizing calculations
├── strategy/               # Strategy domain
│   ├── interfaces.py       # IStrategy interface (on_bar, on_tick, on_fill)
│   ├── value_objects.py    # StrategyConfig, StrategySignal
│   ├── strategy_event.py   # SignalGeneratedEvent
│   └── strategies/         # Concrete strategies
│       └── ma_crossover_strategy.py  # MACrossoverStrategy
├── shared/                 # Shared domain concepts
│   ├── value_objects.py    # Symbol, Interval, Price enums/dataclasses
│   └── events.py           # DomainEvent base class
└── common/                 # Domain utilities (no I/O)
```

**Example - Value Object & Event (Dataclasses, Not Pydantic):**
```python
@dataclass(frozen=True)
class Symbol:  # Immutable value object
    code: str
    exchange: str
    def __post_init__(self) -> None:
        if not self.code or not self.exchange:
            raise ValueError("Both required")

@dataclass(frozen=True, eq=False)
class OrderFilledEvent:  # Event: frozen + custom __eq__ by event_id
    event_id: UUID = field(default_factory=generate_id)
    order_id: UUID = field(default_factory=generate_id)
    price: float

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OrderFilledEvent):
            return NotImplemented
        return self.event_id == other.event_id
```

**Example - Domain Service (Pure):**
```python
class BarBuilder:
    """Incremental OHLCV construction. Zero I/O."""
    def add_tick(self, price: float, volume: float) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += volume

    def is_complete(self) -> bool:
        return time.time() >= self.bar_close_time
```

### Layer 2: Application (Orchestrators) — src/application/

**Purpose:** Orchestrate domain logic + infrastructure I/O to fulfill business use cases. Stateful services and engines that coordinate between layers.

**Structure:**
```
application/
├── backtesting/              # Backtest orchestration
│   ├── backtest_app_service.py   # BacktestAppService engine (execute backtest)
│   ├── grid_optimization_app_service.py    # GridOptimizationAppService (parameter optimization)
│   ├── historical_replay_app_service.py  # Inject historical bars chronologically
│   ├── result_collector.py  # Collect fills, calculate P&L
│   └── models/              # PerformanceCalculator, DTOs
├── market_data/              # Data sync orchestration
│   ├── bar_app_service.py       # BarAppService (real-time multi-interval aggregation)
│   ├── quote_app_service.py     # QuoteAppService (WebSocket lifecycle, tick distribution)
│   ├── sync_jobs.py         # Background sync jobs (APScheduler tasks)
│   └── models/              # DTOs for market data
├── strategy/                 # Strategy orchestration
│   ├── strategy_app_service.py   # StrategyAppService (on_bar/on_tick dispatch, signal handling)
│   └── yaml_strategy_loader.py  # StrategyLoader (YAML → IStrategy instances)
├── trading/                  # Trading orchestration
│   ├── order_app_service.py     # OrderAppService (order state, recovery)
│   └── position_app_service.py  # PositionAppService (position state, P&L aggregation)
└── __init__.py
```

**Example - Application Service:**
```python
# StrategyAppService - orchestrates domain strategy + infrastructure execution
class StrategyAppService:
    def __init__(self, broker: IBroker, event_bus: EventBus):
        self.broker = broker
        self.event_bus = event_bus
        self.strategy: Optional[IStrategy] = None

    async def on_bar(self, bar: OHLCVBar) -> None:
        """Called by BarAppService when new bar completes."""
        # 1. Domain: Get strategy signal
        signal = await self.strategy.on_bar(bar)

        # 2. Domain: Check risk
        approved = await risk_check(signal)

        # 3. Infrastructure: Execute via broker
        if approved:
            order = await self.broker.submit_order(approved.order)

        # 4. Infrastructure: Publish event
        await self.event_bus.publish(SignalGeneratedEvent(...))
```

### Layer 3: Features (CQRS Operation Routes) — src/features/

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
├── market_data/              # Market data feature (7 nested operations)
│   ├── sync/                # Nested group
│   │   ├── sync_one/       # Operation: Sync single symbol
│   │   ├── sync_bulk/      # Operation: Sync multiple symbols
│   │   ├── dto.py
│   │   └── router.py
│   ├── ohlcv/               # Nested group
│   │   ├── get_ohlcv/      # Operation: Get bars
│   │   └── router.py
│   ├── quotes/              # Nested group
│   │   ├── start_feed/     # Operation: Start WebSocket
│   │   ├── stop_feed/      # Operation: Stop WebSocket
│   │   ├── subscribe/      # Operation: Subscribe symbol
│   │   ├── get_all/        # Operation: Get all quotes
│   │   ├── get_latest/     # Operation: Get latest quote
│   │   └── router.py
│   ├── status/              # Nested group
│   │   ├── get_sync_status/
│   │   ├── get_quote_service_status/
│   │   └── router.py
│   ├── list_symbols/        # Operation: List symbols
│   └── router.py
├── strategy/                 # Strategy feature (4 operations)
│   ├── get_all/            # Operation: List strategies
│   ├── get_one/            # Operation: Get strategy
│   ├── load/               # Operation: Load strategy YAML
│   ├── start/              # Operation: Start strategy
│   ├── stop/               # Operation: Stop strategy
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
        bars = await OHLCVRepository.get_bars(cmd.symbol, cmd.start_date, cmd.end_date)

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

### Layer 4: Infrastructure (External I/O) — src/infrastructure/ + src/persistence/

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
├── repositories/            # Data access layers (stateless class methods)
│   ├── ohlcv_repository.py     # OHLCV bar data access
│   ├── order_repository.py     # Order persistence
│   ├── position_repository.py  # Position tracking
│   ├── backtest_repository.py  # Backtest results
│   ├── optimization_repository.py  # Parameter optimization results
│   ├── symbol_repository.py    # Symbol metadata
│   └── sync_status_repository.py   # Data sync status
└── schemas/                 # MongoDB document schemas
    ├── ohlcv_schema.py
    ├── order_schema.py
    ├── position_schema.py
    ├── symbol_schema.py
    └── quote_schema.py
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
| **JobScheduler** | APScheduler wrapper, async job execution |

### Layer 5: Common (Cross-Cutting) — src/common/

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
  ├─ [2] Validate: OHLCVAggregate(bars)             [domain]
  ├─ [3] Persist: OHLCVRepository.upsert_many()     [infrastructure]
  ├─ [4] Invalidate: Cache.delete_pattern()         [infrastructure]
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
HTTP Request (GET /market-data/ohlcv/{exchange}/{symbol}?interval=1d&limit=100)
  ↓
Middleware Stack
  ├─ CorrelationIdMiddleware → inject correlation_id
  ├─ RateLimitMiddleware → check token bucket
  └─ (No idempotency for GET)
  ↓
Route (features/market_data/ohlcv/get_ohlcv/route.py)
  ├─ Parse query params
  ├─ Build GetOHLCVQuery
  └─ Call Mediator.send(query)
  ↓
Mediator (common/mediator/mediator.py)
  ├─ Lookup handler via @handles(GetOHLCVQuery)
  └─ Call handler.handle(query)
  ↓
Handler (features/market_data/ohlcv/get_ohlcv/handler.py)
  ├─ [1] Fetch: Cache.get(key) or OHLCVRepository.get_bars()
  ├─ [2] Validate: OHLCVBar value objects
  ├─ [3] Cache: Cache.set(key, result, ttl=300)
  └─ [4] Return: BarsDTO (never return entities)
  ↓
Route Response
  └─ Return BarsDTO as JSON 200
```

## Trading Persistence Layer

### MongoDB Collections & Repository Access

**Collections available via Persistence Layer:**

| Collection | Purpose | Repository | Key Methods |
|-----------|---------|-----------|------------|
| `ohlcv` | Market bars (OHLCV data) | OHLCVRepository | `get_bars()`, `upsert_many()` |
| `orders` | Order lifecycle | OrderRepository | `save()`, `find_pending()`, `get_by_id()` |
| `positions` | Position tracking | PositionRepository | `save()`, `find_open()`, `get_by_id()` |
| `backtests` | Backtest results | BacktestRepository | `save()`, `find_by_id()`, `list_by_strategy()` |
| `optimizations` | Parameter optimization results | OptimizationRepository | `save()`, `find_by_id()` |
| `symbols` | Symbol metadata | SymbolRepository | `find_by_code()`, `list_all()` |
| `sync_status` | Data sync progress | SyncStatusRepository | `save()`, `find_by_symbol()`, `update_status()` |

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

**Purpose:** Decouple features via domain events (in-memory, FIFO, 100 event max history).

**Characteristics:**
- Handlers publish → EventBus.publish(event) → subscribers notified sequentially
- Bounded history (100 events in container.py, configurable)
- Sync + async handlers supported
- No persistence (events lost on restart)

## Data Pipelines

### Historical Data Sync Pipeline

```
POST /market-data/sync
  ↓
Route → SyncSymbolCommand → Mediator
  ↓
SyncSymbolHandler
  ├─> TradingViewClient.fetch_ohlcv
  │   ├─> ThreadPoolExecutor (blocking I/O isolation)
  │   ├─> tvdatafeed.get_hist(symbol, exchange, interval, n_bars)
  │   └─> Return list[OHLCVBar]
  │
  ├─> OHLCVAggregate(bars)  # Domain validation
  │
  ├─> MongoDB.bulk_write (upsert on timestamp)
  │
  ├─> Redis.delete_pattern(f"ohlcv:{symbol}:*")  # Cache invalidation
  │
  └─> EventBus.publish(BarSyncedEvent(...))

Response: {bars_synced: 100, status: "completed"}
```

### Real-time Quote Pipeline

```
TradingView WebSocket
  ↓
Binary Frame: ~m~{length}~m~{json}
  ↓
TradingViewWebSocketClient.parse_frame
  ↓
QuoteAppService._on_quote_update
  ├─> Redis.set(f"quote:latest:{exchange}:{symbol}", quote, ttl=60)
  │
  ├─> BarAppService.process_tick(quote)
  │   ├─> For each interval (1m, 5m, 15m, ...)
  │   │   ├─> Get/create BarBuilder
  │   │   ├─> Update OHLC (asyncio.Lock for safety)
  │   │   └─> Check time boundary
  │   │
  │   └─> On bar complete:
  │       ├─> MongoDB.insert_one(bar)
  │       ├─> Redis.set(f"bar:current:{exchange}:{symbol}:{interval}", bar)
  │       └─> EventBus.publish(BarCompletedEvent(...))
  │
  └─> EventBus.publish(QuoteReceivedEvent(...))
```

### Strategy Execution Pipeline

```
Market Data Event (BarCompletedEvent or QuoteReceivedEvent)
  ↓
StrategyAppService._on_market_event
  ├─> Validate strategy is running
  │
  ├─> Call strategy.on_bar(bar) or on_tick(quote)
  │   └─> Strategy generates signal: Buy/Sell/Hold
  │
  ├─> RiskCheckHandler.check_signal(signal)
  │   ├─> Check position limits
  │   ├─> Check account limits
  │   └─> Return approved signal or None
  │
  ├─> On approved signal:
  │   ├─> Build Order via OrderBuilder
  │   ├─> Submit order via IBroker.submit_order(order)
  │   ├─> OrderRepository.save(order) - MongoDB persistence
  │   └─> EventBus.publish(OrderSubmittedEvent(...))
  │
  └─> On fill event:
      ├─> PositionAppService._on_order_filled
      │   ├─> Create/update position
      │   ├─> PositionRepository.save(position) - MongoDB persistence
      │   └─> EventBus.publish(PositionOpenedEvent/PositionUpdatedEvent)
      ├─> Calculate P&L
      └─> OrderRepository.save(order) - Persist filled state
```

### Backtesting Pipeline

```
POST /backtest/run
  ↓
BacktestRunCommand → Mediator
  ↓
BacktestHandler
  ├─> Load strategy YAML config
  │
  ├─> Fetch historical bars from MongoDB
  │   └─> Sorted by timestamp (ascending)
  │
  ├─> BacktestAppService.run()
  │   ├─> Initialize PaperBroker
  │   ├─> Initialize StrategyAppService
  │   │
  │   └─> For each bar (chronological):
  │       ├─> Inject bar to StrategyAppService
  │       ├─> Strategy.on_bar(bar) → signal
  │       ├─> RiskCheckHandler.check_signal()
  │       ├─> PaperBroker.submit_order()
  │       ├─> Simulate fill with slippage/delay
  │       ├─> Update PositionAppService
  │       └─> Collect fill events
  │
  ├─> ResultCollector.finalize()
  │   ├─> PerformanceCalculator.calculate()
  │   │   ├─> Sharpe ratio
  │   │   ├─> Sortino ratio
  │   │   ├─> Max drawdown
  │   │   ├─> Win rate
  │   │   └─> Return metrics
  │   │
  │   └─> Store BacktestResult in MongoDB
  │
  └─> Return BacktestResultDTO
```

### Parameter Optimization Pipeline

```
POST /backtest/optimize
  ↓
OptimizationCommand → Mediator
  ↓
OptimizationHandler
  ├─> GridOptimizationAppService.optimize()
  │   ├─> Generate parameter combinations
  │   │
  │   ├─> For each combo (parallel via multiprocessing):
  │   │   ├─> Backtest with params
  │   │   ├─> Collect performance metric (e.g., Sharpe)
  │   │   └─> Return score
  │   │
  │   └─> Return best_params, best_score
  │
  ├─> Store OptimizationResult in MongoDB
  │
  └─> Return OptimizationResultDTO
```

## Concurrency Model

### Event Loop (FastAPI/Uvicorn)

All async code runs on single event loop.

**Proper async:**
```python
await Database.get_collection("ohlcv").find_one()
await Cache.set("key", value)
await Mediator.send(command)
```

### Thread Pool (Blocking I/O)

TradingView REST API (tvdatafeed) is blocking. ThreadPoolExecutor (max 4 workers) prevents event loop blocking.

### Asyncio.Lock (Quote Aggregation)

BarAppService uses lock for thread-safe bar building to prevent race conditions during atomic OHLC updates.

## Dependency Injection (Dishka DI)

dishka library with 6 providers + auto-resolution via type hints. Cleaner than plain constructors — dependencies resolved by matching `__init__` parameter types.

**Key files:**
| File | Purpose |
|------|---------|
| `src/container.py` | Factory: `create_container()`, handler registration |
| `src/di/` | 6 Provider classes: CoreProvider, PersistenceProvider, InfrastructureProvider, MarketDataProvider, TradingProvider, HandlerProvider |
| `src/main.py` | Lifespan: create container, get DB/Cache, register handlers, setup_dishka |

**Provider breakdown:**
- **CoreProvider** - Settings, EventBus, Mediator (app-scoped singletons)
- **PersistenceProvider** - Database, Cache, all 7 repositories
- **InfrastructureProvider** - Brokers, TradingView provider, JobScheduler, HTTP client
- **MarketDataProvider** - BarAppService, QuoteAppService, sync jobs
- **TradingProvider** - OrderAppService, PositionAppService
- **HandlerProvider** - All 27 CQRS handlers (auto-discovered via ALL_HANDLER_TYPES list)

**Handler registration:** `register_handlers(container)` resolves all handler types from container and registers with Mediator.

## Resource Lifecycle

### Startup Sequence

1. `get_settings()` loads config, logging initialized
2. Create dishka AsyncContainer with 6 providers
3. Get Database and Cache from container, store on `app.state` for middleware hot-path
4. `register_handlers(container)` resolves all 27 handlers and registers with Mediator
5. `ensure_all_indexes()` creates MongoDB indexes
6. `register_health_checks()` registers DB/Redis health probes
7. `start_background_jobs()` registers APScheduler jobs
8. `setup_dishka(container, app)` integrates dishka with FastAPI routes
9. Server ready to accept requests

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
| **TradingView REST** | HTTP | tvdatafeed library, ThreadPoolExecutor (4 workers), max 5000 bars |
| **TradingView WS** | Binary | Protocol: ~m~{len}~m~{json}, exponential backoff reconnection |
| **OKX WS** | JSON + Auth | HMAC-SHA256 auth, 1s-30s backoff, 10-failure circuit breaker |
| **MongoDB** | Async | PyMongo (not Motor), pool 5-50 connections, 7 collections |
| **Redis** | Async | redis-py, TTL: 60s quotes, 300s bars, 86400s idempotency |

## Error Handling

| Category | Examples | Strategy |
|----------|----------|----------|
| **Transient** | Connection timeouts, API unavailable | Exponential backoff, auto-reconnect |
| **Permanent** | Invalid symbols, auth failures | Return HTTP errors (4xx/5xx) |
| **Silent** | Background job/cache failures | Log, continue execution |

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Historical Sync | 1-5s per 5000 bars |
| WebSocket Quote | <100ms TradingView→handler |
| Bar Aggregation | <1ms per tick (in-memory) |
| Cache Lookup | <5ms (Redis) |
| Mediator Dispatch | <0.1ms (dict lookup) |
| Concurrent Syncs | 4 workers (ThreadPoolExecutor) |
| Quote Throughput | 1000+ ticks/sec |
| Rate Limit | 200 req/10s per IP |
| Memory (MongoDB Pool) | ~10-20MB per connection |
| Memory (BarAppService) | ~10MB per 10k subscriptions |

## Security
- Credentials: Environment variables only (never committed)
- Auth: MongoDB/Redis via DSN, rate limiting 200 req/10s, idempotency cache 24h TTL
