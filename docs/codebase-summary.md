# Codebase Summary

**Last Updated:** 2026-02-22 | **Codebase Size:** 13,637 LOC | **Total Files:** 277 Python files in src/ | **Architecture:** Clean Architecture + DDD + CQRS + IoC Container

## Architecture Overview

PocketQuant uses **Clean Architecture + DDD + CQRS** with strict unidirectional dependencies:

```
Features (Routes, Commands, Queries, Handlers)
  ↓ depends on
Application (Orchestrators: StrategyEngine, BacktestRunner, BarManager)
  ↓ depends on
Domain (Pure business logic: Aggregates, Value Objects, Events)
  ↑ depended on by
Infrastructure (I/O: Brokers, Providers, Persistence, Scheduling)
```

**Key Characteristics:**
- **Domain Layer:** Pure business logic with ZERO I/O dependencies (enforced via AST checks)
- **Application Layer:** Stateful orchestrators (StrategyEngine, BacktestRunner, BarManager, etc.)
- **Features Layer:** Thin CQRS operation routes (routes → commands/queries → handlers)
- **Infrastructure Layer:** All external I/O (brokers, providers, database, cache, scheduling)
- **Common Layer:** Shared utilities (Mediator, EventBus, middleware, health checks)

## Module Breakdown

### src/common (993 LOC, 32 files)

**Coordinators & Mediator:**
- **Mediator:** CQRS dispatcher, routes commands/queries to handlers
  - `register(request_type, handler)` - Register handler
  - `send(request)` - Dispatch to handler, raises HandlerNotFoundError if missing
- **EventBus:** In-memory async event bus (FIFO, 100 event max history, configured in container.py)
  - `subscribe(event_type, handler)` - Register event subscriber
  - `publish(event)` - Notify all subscribers sequentially
  - `publish_all(events)` - Batch publish multiple events

**Event Handling & Auto-Discovery:**
- **@event_handler decorator** - Mark methods as event subscribers (86 LOC)
- **EventRegistry** - Auto-discover and bind decorated handlers
  - `register_instance(obj, event_bus)` - Scan obj for decorated methods, subscribe all
  - Supports single or multiple event types per handler
  - Returns count of registered handlers for verification

**Tracing & Middleware:**
- **CorrelationIDMiddleware** - Inject correlation_id into context for request tracking
- **RequestLoggingMiddleware** - Log all requests/responses with correlation IDs
- `get_correlation_id()` - Access current correlation ID in async context
- **IdempotencyMiddleware** - Cache POST responses by idempotency_key header (24h TTL)
- **RateLimitMiddleware** - Token bucket (100 capacity, 10 tokens/sec refill) per IP

**UUID Utilities:**
- **uuid.py** - UUID7 generation (19 LOC)
  - `generate_id()` - Return UUID v7 (time-ordered)
  - `generate_id_str()` - Return UUID v7 as string
  - Replaces UUID4 for better database performance (chronological sorting)

**Infrastructure Singletons:**
- **Database** - Async MongoDB singleton (PyMongo native async API)
  - `get_collection(name)` - Access collection
  - `connect(settings)` - Initialize connection pool (5-50 connections)
  - `disconnect()` - Clean shutdown
- **Cache** - Async Redis singleton (redis-py async)
  - `get(key)`, `set(key, value, ttl=None)`, `delete(key)`
  - `delete_pattern(pattern)` - Pattern-based deletion via SCAN
  - `get_or_set(key, func, ttl)` - Cache-aside pattern
- **HealthCoordinator** - Parallel health checks (database, redis, jobs)
- **JobScheduler** - APScheduler wrapper (AsyncIOExecutor)

**Logging & Constants:**
- `setup_logging()` - structlog with JSON/console output
- `get_correlation_id()` - Thread/async-safe context variable access
- **constants.py** - Centralized cache keys, TTLs, limits, headers, interval mappings

### src/domain (2,364 LOC, 39 files) — Pure Business Logic

**Rules:** No I/O imports. No pymongo, redis, aiohttp. **No Pydantic BaseModel** (use stdlib dataclasses instead). Immutable value objects. Domain events. Validation in `__post_init__`.

**Aggregates (6, Mutable Dataclasses):**
- **OHLCVAggregate** - Collection of OHLCV bars with validation (mutable @dataclass)
- **OrderAggregate** - Order lifecycle state machine (UUID7 IDs, mutable @dataclass)
- **PositionAggregate** - Position tracking with P&L calculations (UUID7 IDs, mutable @dataclass)
- **QuoteAggregate** - Quote with metadata (field: updated_at, mutable @dataclass)
- **SymbolAggregate** - Symbol with exchange metadata (UUID7 IDs, mutable @dataclass)
- **RiskConfigAggregate** - Risk parameters and position sizing (UUID7 IDs, mutable @dataclass)

**Value Objects (Frozen Dataclasses, @dataclass(frozen=True)):**
- **OHLCV** - (open, high, low, close, volume, timestamp) with validation in __post_init__
- **BarRange** - (start_time, end_time) for bar alignment
- **PnL** - (unrealized, realized, total)
- **Signal** - Buy/sell signal with quantity
- **SymbolInfo** - (code, exchange, name, description)
- **Price** - Decimal price wrapper
- **QuoteTick** - Real-time price update
- **RiskConfig** - Risk model + parameters
- **Symbol** - (code, exchange) value object with validation

**Enums:**
- **OrderType** - MARKET, LIMIT, STOP_LIMIT, STOP_MARKET
- **OrderSide** - BUY, SELL
- **OrderStatus** - PENDING, PARTIAL_FILL, FILLED, CANCELLED, REJECTED, ERROR (6 states with is_terminal, is_active)
- **PositionSide** - LONG, SHORT
- **Direction** - LONG, SHORT, EXIT, FLAT
- **RiskModel** - PERCENT_RISK, KELLY, FIXED
- **Interval** - 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M (13 timeframes)

**Domain Events (13+, Frozen Dataclasses with @dataclass(frozen=True, eq=False)):**
- **OHLCV:** HistoricalDataSyncedEvent, BarCompletedEvent
- **Order:** OrderSubmittedEvent, OrderFilledEvent, OrderPartiallyFilledEvent, OrderCancelledEvent, OrderRejectedEvent
- **Position:** PositionOpenedEvent, PositionUpdatedEvent, PositionClosedEvent
- **Quote:** QuoteReceivedEvent, QuoteUpdatedEvent
- **Strategy:** SignalGeneratedEvent
- All events extend DomainEvent base (frozen dataclass with custom __eq__ by event_id)

**Domain Services:**
- **BarBuilder** - Incremental OHLCV bar construction from ticks
  - `add_tick(price, volume)` - Update bar with new tick
  - `is_complete()` - Check if bar period elapsed
  - `to_dict()` - Export bar as dict
- **PositionSizer** - Calculate position size by risk model
  - `calculate_size(account_balance, signal)` - Returns quantity
  - Supports: PERCENT_RISK, KELLY, FIXED

### src/application (2,559 LOC, 21 files) — Orchestrators

Stateful services that coordinate domain logic + infrastructure:
- **BacktestRunner:** Execute strategy on historical bars
- **GridOptimizer:** Parameter optimization (multiprocessing)
- **BarManager:** Real-time multi-interval bar aggregation
- **QuoteService:** WebSocket lifecycle, tick distribution
- **StrategyEngine:** Strategy dispatch (on_bar, on_tick, on_fill)
- **OrderManager:** Order state machine + recovery
- **PositionTracker:** Position state, P&L calculation
- **StrategyLoader:** YAML → IStrategy instantiation

No CQRS in this layer. These are business orchestrators called by CQRS handlers.

### src/infrastructure (2,883 LOC, 28 files) — External I/O & Brokers

**Brokers (Pluggable Execution):**
- **IBroker** - Abstract contract
  - `connect()`, `disconnect()` - Lifecycle
  - `submit_order(symbol, side, type, quantity, price)` - Place order
  - `cancel_order(order_id)` - Cancel by ID
  - `get_balance()` - Account balance
  - `get_positions()` - Open positions
- **PaperBroker** - In-memory simulation
  - Slippage simulation (configurable % or fixed points)
  - Fill delay (configurable milliseconds)
  - Position tracking with entry/exit prices
  - P&L calculations
  - `set_current_price(symbol, price)` - Update price for fills
- **OKXBroker** - OKX live trading
  - REST API + WebSocket integration
  - HMAC-SHA256 authentication
  - Demo mode support
- **BrokerFactory** - Factory pattern
  - `create(type, config)` → IBroker (paper, okx)

**OKX WebSocket Integration:**
- **OkxWebSocketClient** - Low-level WebSocket handler
  - HMAC login authentication
  - Heartbeat (25s ping)
  - Binary frame parsing
  - Async iterator interface
- **OkxReconnectionHandler** - Resilient connection management
  - Exponential backoff (1s → 30s max)
  - Circuit breaker (10 failures → 5m pause)
  - Automatic re-subscription on reconnect
- **Mappers:** OkxOrderMapper, OkxPositionMapper for state translation

**Data Providers:**
- **TradingViewProvider** - REST API (tvdatafeed)
  - ThreadPoolExecutor (max 4 workers) for blocking I/O
  - `fetch_ohlcv(symbol, exchange, interval, n_bars)` - Fetch historical bars
- **TradingViewWebSocketProvider** - Binary WebSocket protocol
  - Custom frame format parsing (~m~{len}~m~{json})
  - Quote streaming
  - Auto-reconnection
- **IDataProvider** - Abstract interface for providers

**Scheduling:**
- **JobScheduler** - APScheduler wrapper
  - AsyncIOExecutor for async jobs
  - In-memory job store (non-persistent)
  - `add_interval_job(func, interval)` - Periodic execution
  - `add_cron_job(func, cron_expr)` - Scheduled execution
  - Coalesce=True (skip missed runs)

**HTTP & Webhooks:**
- Generic async HTTP client (aiohttp)
- **WebhookDispatcher** - Event notifications
  - HMAC-SHA256 signing
  - Resilient delivery with retry

### src/persistence (1,214 LOC, 18 files) — Data Access Layer

**Database Connections (Instance-Based via DI):**
- **Database** - Async MongoDB wrapper
  - PyMongo native async API (NOT Motor)
  - Connection pooling (5-50 connections, configurable)
  - Single `get_collection()` entry point
  - Injected via DI container
- **Cache** - Async Redis client
  - JSON serialization with custom date handling
  - TTL support (60s quotes, 300s bars, 86400s idempotency)
  - Pattern-based deletion via SCAN
  - Injected via DI container

**BaseRepository Mixin:**
- `_collection(name)` - Get MongoDB collection safely
- Ensures all repositories use connection pooling
- Zero direct `Database.get_collection()` calls outside persistence/

**Repositories (7 stateless data access layers):**
1. **OHLCVRepository** - Market bar persistence
   - `get_bars(symbol, exchange, interval, limit)` - Query bars
   - `upsert_many(records)` - Bulk insert/update (unique on timestamp)
2. **OrderRepository** - Order lifecycle
   - `save(order)` - Persist order state
   - `find_pending()` - Recover non-terminal orders on startup
   - `get_by_id(order_id)` - Fetch single order
3. **PositionRepository** - Position tracking
   - `save(position)` - Persist position state
   - `find_open()` - Recover open positions on startup
   - `get_by_id(position_id)` - Fetch single position
4. **BacktestRepository** - Backtest result storage
   - `save(result)` - Store completed backtest
   - `find_by_id(run_id)` - Retrieve backtest
   - `list_by_strategy(strategy_id)` - Query strategy backtests
5. **OptimizationRepository** - Parameter optimization results
   - `save(result)` - Store optimization result
   - `find_by_id(optimization_id)` - Retrieve result
6. **SymbolRepository** - Symbol metadata
   - `find_by_code(code, exchange)` - Lookup symbol
   - `list_all()` - Get all symbols
7. **SyncStatusRepository** - Data sync progress tracking
   - `save(status)` - Record sync status
   - `find_by_symbol(symbol, exchange)` - Get last sync
   - `update_status(status_id, progress, error)` - Update progress

**MongoDB Schemas (Document validation):**
- ohlcv_schema.py - Bar structure (open, high, low, close, volume, timestamp)
- order_schema.py - Order fields (status, symbol, exchange, quantity, price, etc.)
- position_schema.py - Position fields (symbol, exchange, side, quantity, entry_price, etc.)
- symbol_schema.py - Symbol metadata (code, exchange, name, description)
- quote_schema.py - Quote structure (symbol, exchange, price, volume, timestamp)

### src/features (3,016 LOC, 134 files) — CQRS Operation Routes

**Vertical Slice Architecture (Operation-First Pattern):**
Each feature is self-contained. Operations are the primary organizational unit. Routes are thin (parse request, call handler, return response). All business logic delegated to handlers.

**Dependency:** Features depend on Application + Domain + Infrastructure.
**No reverse dependencies:** Domain never imports from Features.

**backtesting/ (626 LOC, 22 files)**

Structure:
```
backtesting/
├── base/                 # Shared infrastructure
│   ├── engine/          # BacktestRunner, HistoricalReplayEngine
│   ├── metrics/         # PerformanceCalculator
│   ├── models/          # DTOs
│   ├── optimizer/       # GridOptimizer
│   └── repository/      # BacktestRepository
├── run/                 # Operation: Execute backtest
│   ├── command.py
│   ├── handler.py
│   └── route.py
├── optimize/            # Operation: Optimize parameters
│   ├── command.py
│   ├── handler.py
│   └── route.py
├── get_result/          # Operation: Retrieve backtest
│   ├── query.py
│   ├── handler.py
│   └── route.py
├── get_optimization/    # Operation: Get optimization
│   ├── query.py
│   └── handler.py
├── list_results/        # Operation: List backtests
│   ├── query.py
│   └── handler.py
└── router.py            # Main feature router
```

Routes:
- POST `/api/v1/backtest/run` - Execute backtest
- POST `/api/v1/backtest/optimize` - Parameter optimization
- GET `/api/v1/backtest/{run_id}` - Retrieve results
- GET `/api/v1/backtest/optimization/{id}` - Optimization results
- GET `/api/v1/backtest/strategy/{id}` - Strategy results

**market_data/ (1,534 LOC, 68 files)**

Structure:
```
market_data/
├── base/                # Shared infrastructure
│   ├── jobs/           # Background job definitions
│   ├── managers/       # BarManager
│   ├── models/         # DTOs
│   ├── providers/      # Data providers
│   └── services/       # Sync service
├── sync/                # Sync feature (nested)
│   ├── sync_one/       # Operation: Sync single
│   │   ├── command.py
│   │   ├── handler.py
│   │   └── route.py
│   ├── sync_bulk/      # Operation: Sync bulk
│   │   ├── command.py
│   │   ├── handler.py
│   │   └── route.py
│   ├── dto.py
│   └── router.py
├── ohlcv/               # OHLCV feature (nested)
│   ├── get_ohlcv/      # Operation: Get bars
│   │   ├── query.py
│   │   ├── handler.py
│   │   └── route.py
│   └── router.py
├── quotes/              # Quotes feature (nested)
│   ├── get_all/        # Operation: Get all quotes
│   ├── get_current_bar/
│   ├── get_latest/
│   ├── start_feed/
│   ├── stop_feed/
│   ├── subscribe/
│   ├── unsubscribe/
│   └── router.py
├── status/              # Status feature (nested)
│   ├── get_quote_service_status/
│   ├── get_symbol_sync_status/
│   ├── get_sync_status/
│   └── router.py
├── list_symbols/        # Operation: List symbols
│   ├── query.py
│   ├── handler.py
│   └── route.py
├── repositories/        # Data access
│   ├── ohlcv_repository.py
│   ├── symbol_repository.py
│   └── sync_status_repository.py
└── router.py            # Main feature router
```

Routes:
- POST `/api/v1/market-data/sync` - Single symbol sync
- POST `/api/v1/market-data/sync/bulk` - Bulk sync
- GET `/api/v1/market-data/ohlcv/{exchange}/{symbol}` - Query bars
- GET `/api/v1/market-data/symbols` - List symbols
- POST `/api/v1/quotes/start` - Start WebSocket
- POST `/api/v1/quotes/stop` - Stop WebSocket

**strategy/ (416 LOC, 22 files)**

Structure:
```
strategy/
├── base/                # Shared infrastructure
│   ├── engine/         # StrategyEngine
│   ├── interfaces/     # IStrategy interface
│   └── loader/         # YAML loader
├── get_all/            # Operation: List strategies
│   ├── query.py
│   ├── handler.py
│   └── route.py
├── get_one/            # Operation: Get strategy
│   ├── query.py
│   └── handler.py
├── load/               # Operation: Load strategy
│   ├── command.py
│   ├── handler.py
│   └── route.py
├── start/              # Operation: Start strategy
│   ├── command.py
│   ├── handler.py
│   └── route.py
├── stop/               # Operation: Stop strategy
│   ├── command.py
│   ├── handler.py
│   └── route.py
└── router.py           # Main feature router
```

Routes:
- GET `/api/v1/strategies` - List strategies
- POST `/api/v1/strategies/load` - Load strategy
- POST `/api/v1/strategies/start` - Start strategy
- POST `/api/v1/strategies/stop` - Stop strategy

**trading/ (281 LOC, 18 files)**

Structure:
```
trading/
├── base/                # Shared infrastructure
│   ├── managers/       # OrderManager, PositionTracker
│   ├── models/         # DTOs
│   └── repositories/   # OrderRepository, PositionRepository
├── list_orders/        # Operation: List orders
│   ├── query.py
│   ├── handler.py
│   └── route.py
├── get_order/          # Operation: Get order
│   ├── query.py
│   └── handler.py
├── list_positions/     # Operation: List positions
│   ├── query.py
│   ├── handler.py
│   └── route.py
├── get_position/       # Operation: Get position
│   ├── query.py
│   └── handler.py
└── router.py           # Main feature router
```

Routes:
- GET `/api/v1/orders` - List orders
- GET `/api/v1/orders/{order_id}` - Get order
- GET `/api/v1/positions` - List positions

**risk/ (158 LOC, 3 files)**

Structure:
```
risk/
├── check_risk/         # Operation: Check risk
│   ├── command.py
│   ├── handler.py
│   └── route.py
└── __init__.py
```

Routes:
- POST `/api/v1/risk/check` - Pre-trade validation

## CQRS Flow

```
1. Route receives HTTP request
   ↓
2. Route builds Command/Query object
   ↓
3. Route calls Mediator.send(request)
   ↓
4. Mediator dispatches to registered Handler
   ↓
5. Handler executes business logic:
   - Fetch data from Infrastructure
   - Process via Domain layer
   - Save results via Infrastructure
   - Publish DomainEvents to EventBus
   ↓
6. Handler returns DTO
   ↓
7. Route converts DTO to HTTP response
```

## Data Pipelines

### Historical Data Pipeline

```
POST /market-data/sync
    ↓
SyncSymbolCommand → Mediator → SyncSymbolHandler
    ├─> TradingViewProvider.fetch_ohlcv (thread pool)
    ├─> Domain validation via OHLCVAggregate
    ├─> MongoDB bulk_write (upsert)
    ├─> Redis cache invalidation (pattern delete)
    └─> EventBus.publish(HistoricalDataSyncedEvent)
```

### Real-time Quote Pipeline

```
TradingView WebSocket → TradingViewWebSocketProvider
    ↓
Parse binary frame → QuoteService._on_quote_update
    ├─> Redis cache (60s TTL)
    ├─> BarManager.process_tick (multi-interval aggregation)
    │   ├─> Build OHLCV bars (1m, 5m, 15m, ..., 1M)
    │   ├─> Detect bar completion
    │   └─> MongoDB save on complete
    └─> EventBus.publish(QuoteReceivedEvent)
```

### Background Job Pipeline

```
APScheduler triggers job (6-hourly or market hours)
    ↓
sync_all_symbols job (each symbol independently)
    ├─> TradingViewProvider.fetch_ohlcv
    ├─> OHLCVRepository.upsert_many
    └─> Error logging per symbol (don't break loop)
```

## Key Patterns

**CQRS (Command Query Responsibility Segregation):**
- Commands mutate state, Queries read-only
- Separate handlers for each command/query type
- Routes build requests, Mediator dispatches to handlers
- Returns DTOs (not entities)

**Event Bus Pattern:** Decoupled domain events
- Handlers publish domain events to EventBus
- Subscribers react asynchronously (FIFO order)
- In-memory with bounded history (50 events)
- No direct coupling between features

**Value Objects:** Immutable domain primitives
- Symbol, Interval, OHLCVBar, QuoteTick, Price
- Frozen dataclasses for immutability
- Validation in __post_init__
- 20+ immutable value objects in codebase

**Mediator Pattern:** Single entry point for all requests
- Routes only parse requests and call Mediator
- Decouples routes from handlers
- Testable in isolation
- Centralized handler registration

**Broker Abstraction:** Pluggable execution layer
- IBroker interface for order execution
- PaperBroker: in-memory simulation with slippage/delays
- OKXBroker: live trading via OKX WebSocket
- StrategyEngine routes signals to broker

**Domain Purity:** Zero I/O in domain layer
- Domain layer contains only business rules
- No pymongo, redis, aiohttp imports allowed
- Validation via test_domain_purity.py (AST check)
- Pure, testable, reusable logic

## Testing Strategy

**Unit Tests:**
- `tests/unit/common/` - Mediator, EventBus, middleware
- `tests/unit/domain/` - Value objects, aggregates, services
- `tests/unit/features/` - Handler tests with mocks

**Domain Purity Test:**
- AST parser checks for forbidden imports in `src/domain/`
- Forbidden: pymongo, redis, aiohttp, src.infrastructure imports
- Ensures domain layer has zero I/O dependencies

**Integration Tests:**
- Route tests with real DB/Cache (mocked)
- CQRS flow validation

## Configuration

All settings via environment variables (`.env` file):
- `MONGODB_URL` - MongoDB DSN
- `REDIS_URL` - Redis DSN
- `LOG_FORMAT` - "json" (prod) or "console" (dev)
- `LOG_LEVEL` - log level (debug, info, warning, error)
- `TRADINGVIEW_USERNAME` - Optional TradingView auth
- `TRADINGVIEW_PASSWORD` - Optional TradingView auth
- `ENVIRONMENT` - "development" or "production"
- `API_PORT` - API server port (default: 8765)

## Dependencies

- **fastapi** - Web framework
- **pydantic** - Settings validation + Features layer (commands/queries). Domain layer uses stdlib dataclasses instead.
- **pymongo** - MongoDB driver (native async API, NOT Motor)
- **redis** - Async Redis client (redis-py)
- **structlog** - Structured logging
- **apscheduler** - Job scheduling (APScheduler)
- **dependency-injector** - IoC container
- **tvdatafeed** - TradingView data source
- **aiohttp** - Async HTTP + WebSocket
- **pytest** - Testing framework
- **ruff** - Linting & formatting
- **pyright** - Type checking

## Entry Points

- **Development:** `python -m src.main` (config via `.env`)
- **Production:** `python -m src.main` with `ENVIRONMENT=production`
- **API Documentation:** `http://localhost:$API_PORT/api/v1/docs`
- **Health Check:** `http://localhost:$API_PORT/health`

## Recent Changes (2026-02-21)

**Documentation Accuracy Refresh:**
- Verified all LOC counts (13,641 across 277 files, not 14,393 across 213)
- Fixed Motor → PyMongo references (using native async API)
- Corrected EventBus max_history (100 events, not 50)
- Fixed justfile commands: `just up/down` (not start/stop/logs)
- Updated type checker reference: pyright (not mypy)
- Updated all docs: README.md, code-standards.md, codebase-summary.md, system-architecture.md, project-overview-pdr.md
- Added Application layer to architecture breakdown
- Added DI container documentation
- Updated feature LOC breakdown with accurate file counts

**Previous Changes (2026-02-14):**
- Clean Architecture Refactor Complete: Domain → Application → Features, Infrastructure ← Domain
- Persistence Layer Refactor: `src/persistence/` top-level package with 7 repositories
- Domain purity enforced via AST checks
- Auto-discovery: @handles + @event_handler decorators

**Earlier Changes (2026-02-12):**
- Event handler auto-discovery: `@event_handler` decorator + `EventRegistry`
- UUID7 migration: All aggregates use time-ordered UUIDs
- QuoteAggregate field rename: `last_update` → `updated_at`

## Known Limitations

- In-memory EventBus (events lost on crash; use for non-critical events)
- In-memory job store (jobs lost on restart; reschedule on startup)
- No persistent outbox pattern (consider for mission-critical systems)
- Rate limiting state lost on Redis restart (acceptable for burst protection)
- Single-threaded strategy execution (one strategy per process)
- Domain purity enforced via AST check (cannot use I/O in domain/)
