# Codebase Summary

**Last Updated:** 2026-04-07 | **Codebase Size:** ~14,751 LOC Python + ~1,414 LOC TypeScript | **Total Files:** 295 Python + 25 TypeScript | **Architecture:** Clean Architecture + DDD + CQRS + Dishka (backend); React 19 SPA (frontend) | **Structure:** 5-package monorepo (uv workspace + npm)

## Architecture Overview

PocketQuant uses **Clean Architecture + DDD + CQRS** with strict unidirectional dependencies:

```
Features (Routes, Commands, Queries, Handlers)
  ↓ depends on
Application (Orchestrators: StrategyAppService, BacktestAppService, BarAppService)
  ↓ depends on
Domain (Pure business logic: Aggregates, Value Objects, Events)
  ↑ depended on by
Infrastructure (I/O: Brokers, Providers, Persistence, Scheduling)
```

**Key Characteristics:**
- **Domain Layer:** Pure business logic with ZERO I/O dependencies (enforced via AST checks)
- **Application Layer:** Stateful orchestrators (StrategyAppService, BacktestAppService, BarAppService, etc.)
- **Features Layer:** Thin CQRS operation routes (routes → commands/queries → handlers)
- **Infrastructure Layer:** All external I/O (brokers, providers, database, cache, scheduling)
- **Common Layer:** Shared utilities (Mediator, EventBus, middleware, health checks)

## Module Breakdown

### pocketquant-web (TypeScript, 25 files, ~1,414 LOC) — React SPA

**Purpose:** Real-time charting UI for market data visualization with technical indicators and backtest visualization.

**Tech Stack:** Vite 8, React 19, TypeScript 5.9, Lightweight Charts 5.1, TanStack Query 5.95, SMA/EMA indicators

**Components:**
- **TradingChart:** Candlestick + volume + 5 technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands)
- **SymbolSelector:** Dropdown for instrument selection with available symbols
- **IntervalSelector:** Timeframe picker (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M)
- **StrategySelector:** Choose strategy for backtesting
- **IndicatorToggles:** Show/hide overlay indicators on chart
- **AppHeader:** Navigation and branding

**Hooks:**
- `useOHLCV()` - Fetch historical bars via TanStack Query with caching
- `useBacktest()` - Execute and track backtest runs
- `useSymbols()` - List available symbols
- `useAvailableIntervals()` - Get compatible timeframes
- `useRealTimeBar()` - Poll API for latest bar (5-10s interval)
- `useIndicators()` - Calculate indicator values from bars

**API Layer:** `apiFetch.ts` wraps fetch + error handling; proxies `/api/*` to `:41920`.

**Deployment:** Vite builds to `dist/`, served as static assets via FastAPI.

### pocketquant.core.common (993 LOC, 32 files)

**CQRS & Mediator:**
- **Mediator:** CQRS dispatcher, routes commands/queries to handlers
  - `register(request_type, handler)` - Register handler
  - `send(request)` - Dispatch to handler, raises HandlerNotFoundError if missing
- **HandlerRegistry** - Batch register multiple handlers
  - `register_all(mediator, handlers)` - Register handler list at startup
- **EventBus:** In-memory async event bus (FIFO, **100 event max history**)
  - `subscribe(event_type, handler)` - Register event subscriber
  - `publish(event)` - Notify all subscribers sequentially
  - `publish_all(events)` - Batch publish multiple events

**Event Handling & Auto-Discovery:**
- **@event_handler decorator** - Mark methods as event subscribers
- **EventRegistry** - Auto-discover and bind decorated handlers
  - `register_instance(obj, event_bus)` - Scan obj for decorated methods, subscribe all
  - Supports single or multiple event types per handler

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
  - `disconnect()` - Clean shutdown (called by dishka provider cleanup)
- **Cache** - Async Redis singleton (redis-py async)
  - `get(key)`, `set(key, value, ttl=None)`, `delete(key)`
  - `delete_pattern(pattern)` - Pattern-based deletion via SCAN
  - `get_or_set(key, func, ttl)` - Cache-aside pattern
  - `disconnect()` - Clean shutdown (called by dishka provider cleanup)
- **HealthCoordinator** - Parallel health checks (database, redis, jobs)
- **JobScheduler** - APScheduler wrapper (AsyncIOExecutor)
  - `shutdown(wait=True)` - Clean shutdown (called by dishka provider cleanup)

**Logging & Constants:**
- `setup_logging()` - structlog with JSON/console output
- `get_correlation_id()` - Thread/async-safe context variable access
- **constants.py** - Centralized cache keys, TTLs, limits, headers, interval mappings

### pocketquant.core.domain (~900 LOC entities + concepts, 39 files) — Pure Business Logic + Persistence

**Rules:** No I/O imports (pymongo, redis, aiohttp). **Pydantic BaseModel with MongoDB persistence.** Aggregates have `to_mongo()` and `from_mongo()` methods. Immutable value objects. Domain events. Validation in `__post_init__`.

**Statistics:**
- domain/ folder: ~355 LOC (Bar 382, Order 382, Position 298, Symbol 81, SyncStatus 51, shared 63)
- concepts/ folder: ~545 LOC (quote 70, risk 167, strategy 383 including MACrossover 159, HitAndRun 156)

**Domain Structure (Three-Tier DDD):**
- **Top-level** (collection-backed): bar/, order/, position/, symbol/, sync_status/, backtest/
- **concepts/** (non-persisted): quote/, risk/, strategy/
- **shared/** (cross-cutting): enums.py, events.py, value_objects.py

**Aggregates (2, Pydantic + MongoDB):**
- **OrderAggregate** - Order state machine with `to_mongo()` / `from_mongo()`
- **PositionAggregate** - Position tracking + P&L with `to_mongo()` / `from_mongo()`

**Entities (5, Pydantic + MongoDB):**
- **Bar** - OHLCV price bar (renamed from OHLCVAggregate)
- **Symbol** - Tradeable instruments (flattened from SymbolAggregate)
- **SyncStatus** - Data sync progress tracking
- **BacktestResult** - Backtest run results
- **OptimizationResult** - Parameter optimization results

**Deleted (Dead Code, 2026-03-15):**
- OHLCVAggregate, QuoteAggregate, SymbolAggregate (no state/invariants)
- persistence/schemas/ directory (logic moved to entities)

**Value Objects (Frozen Dataclasses, @dataclass(frozen=True)):**
- **OHLCV** - (open, high, low, close, volume, timestamp) with validation in __post_init__
- **BarRange** - (start_time, end_time) for bar alignment
- **PnL** - (unrealized, realized, total)
- **Signal** - Buy/sell signal with quantity
- **Price** - Decimal price wrapper
- **QuoteTick** - Real-time price update
- **RiskConfig** - Risk model + parameters

**Enums:**
- **OrderType** - MARKET, LIMIT, STOP_LIMIT, STOP_MARKET
- **OrderSide** - BUY, SELL
- **OrderStatus** - PENDING, PARTIAL_FILL, FILLED, CANCELLED, REJECTED, ERROR (6 states with is_terminal, is_active)
- **PositionSide** - LONG, SHORT
- **Direction** - LONG, SHORT, EXIT, FLAT
- **RiskModel** - PERCENT_RISK, KELLY, FIXED
- **Interval** - 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M (13 timeframes)

**Domain Events (11, Frozen Dataclasses with @dataclass(frozen=True, eq=False)):**
- **Bar:** HistoricalDataSyncedEvent, BarCompletedEvent (emitted from live BarAppService._save_completed_bar())
- **Order:** OrderSubmittedEvent, OrderFilledEvent, OrderPartiallyFilledEvent, OrderCancelledEvent, OrderRejectedEvent
- **Position:** PositionOpenedEvent, PositionUpdatedEvent, PositionClosedEvent
- **Quote:** QuoteReceivedEvent
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

### pocketquant.backtest (submodule) + pocketquant.trading (submodule) (2,559 LOC, 21 files) — Orchestrators

Stateful services that coordinate domain logic + infrastructure:
- **BacktestAppService:** Execute strategy on historical bars
- **GridOptimizationAppService:** Parameter optimization (multiprocessing)
- **BarAppService:** Real-time multi-interval bar aggregation
- **QuoteAppService:** WebSocket lifecycle, tick distribution
- **StrategyAppService:** Strategy dispatch (on_bar, on_tick, on_fill)
- **OrderAppService:** Order state machine + recovery
- **PositionAppService:** Position state, P&L calculation
- **StrategyLoader:** YAML → IStrategy instantiation

No CQRS in this layer. These are business orchestrators called by CQRS handlers.

### pocketquant.core.infrastructure (2,883 LOC, 28 files) — External I/O & Brokers

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
- **TradingViewClient** - REST API (tvdatafeed)
  - ThreadPoolExecutor (max 4 workers) for blocking I/O
  - `fetch_ohlcv(symbol, exchange, interval, n_bars)` - Fetch historical bars
- **TradingViewWebSocketClient** - Binary WebSocket protocol
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

### pocketquant.core.persistence (1,214 LOC, 18 files) — Data Access Layer

**Database Connections (Instance-Based via DI):**
- **Database** - Async MongoDB wrapper
  - PyMongo native async API (NOT Motor)
  - Connection pooling (5-50 connections, configurable)
  - Single `get_collection()` entry point
  - Constructed in lifespan, stored in Services dataclass
- **Cache** - Async Redis client
  - JSON serialization with custom date handling
  - TTL support (60s quotes, 300s bars, 86400s idempotency)
  - Pattern-based deletion via SCAN
  - Constructed in lifespan, stored in Services dataclass

**BaseRepository Mixin:**
- `_collection(name)` - Get MongoDB collection safely
- Ensures all repositories use connection pooling
- Zero direct `Database.get_collection()` calls outside persistence/

**Repositories (7, instance-based via DI):**
1. **BarRepository** - Market bar persistence (renamed from OHLCVRepository)
   - Uses `Bar.to_mongo()` / `Bar.from_mongo()` for serialization
   - `get_bars(symbol, exchange, interval, limit)` - Query bars
   - `upsert_many(records)` - Bulk insert/update (unique on timestamp)
2. **OrderRepository** - Order lifecycle with OrderAggregate persistence
   - `save(order)` - Persist order state
   - `find_pending()` - Recover non-terminal orders on startup
   - `get_by_id(order_id)` - Fetch single order
3. **PositionRepository** - Position tracking with PositionAggregate persistence
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
6. **SymbolRepository** - Symbol metadata with Symbol entity persistence
   - `find_by_code(code, exchange)` - Lookup symbol
   - `find_all()` - Get all symbols
7. **SyncStatusRepository** - Data sync progress tracking
   - `save(status)` - Record sync status
   - `find_by_symbol(symbol, exchange)` - Get last sync
   - `update_status(status_id, progress, error)` - Update progress

**Persistence Consolidation (2026-03-15):**
- `persistence/schemas/` directory DELETED
- All persistence logic consolidated into domain entities via `to_mongo()` / `from_mongo()`
- Repositories import domain entities directly: `from pocketquant.core.domain.bar.entities import Bar`
- Result: Single source of truth (entities), no schema duplication
- Database uses PyMongo (native async), NOT Motor

### pocketquant.api.features (3,016 LOC, 134 files) — CQRS Operation Routes

**Vertical Slice Architecture (Operation-First Pattern):**
Each feature is self-contained. Operations are the primary organizational unit. Routes are thin (parse request, call handler, return response). All business logic delegated to handlers.

**Dependency:** Features depend on Application + Domain + Infrastructure.
**No reverse dependencies:** Domain never imports from Features.

**backtesting/ (626 LOC, 22 files)**

Structure:
```
backtesting/
├── base/                 # Shared infrastructure
│   ├── engine/          # BacktestAppService, HistoricalReplayAppService
│   ├── metrics/         # PerformanceCalculator
│   ├── models/          # DTOs
│   ├── optimizer/       # GridOptimizationAppService
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
│   ├── managers/       # BarAppService
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
├── bar/                 # Bar feature (nested) - renamed from ohlcv/
│   ├── get_bars/       # Operation: Get bars
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
│   ├── bar_repository.py
│   ├── symbol_repository.py
│   └── sync_status_repository.py
└── router.py            # Main feature router
```

Routes:
- POST `/api/v1/market-data/sync` - Single symbol sync
- POST `/api/v1/market-data/sync/bulk` - Bulk sync
- GET `/api/v1/market-data/bar/{exchange}/{symbol}` - Query bars (path renamed from ohlcv)
- GET `/api/v1/market-data/symbols` - List symbols
- POST `/api/v1/quotes/start` - Start WebSocket
- POST `/api/v1/quotes/stop` - Stop WebSocket

**strategy/ (416 LOC, 22 files)**

Structure:
```
strategy/
├── base/                # Shared infrastructure
│   ├── engine/         # StrategyAppService
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
│   ├── managers/       # OrderAppService, PositionAppService
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

## Dependency Injection (Dishka)

### 6 Providers (packages/pocketquant-api/src/pocketquant/api/di/)

**CoreProvider** - App-level singletons
- Settings (from config)
- EventBus (max_history=**100**)
- Mediator

**PersistenceProvider** - Data access layer
- Database (MongoDB, PyMongo native async)
- Cache (Redis, redis-py)
- 7 Repositories (BarRepository, OrderRepository, PositionRepository, BacktestRepository, OptimizationRepository, SymbolRepository, SyncStatusRepository)

**InfrastructureProvider** - External integrations
- IBroker implementations (PaperBroker, OKXBroker)
- BrokerFactory (creates broker by type)
- TradingViewClient (REST data fetching)
- TradingViewWebSocketClient (WebSocket quotes)
- OkxWebSocketClient + OkxReconnectionHandler (OKX integration)
- HTTP client (generic async HTTP)
- WebhookDispatcher

**MarketDataProvider** - Real-time data services
- BarAppService (multi-interval aggregation)
- QuoteAppService (WebSocket lifecycle)
- Sync background jobs (APScheduler registration)

**TradingProvider** - Order/position management
- OrderAppService (order state machine)
- PositionAppService (position tracking + P&L)

**HandlerProvider** - All 27 CQRS handlers
- Market data handlers (13): SyncSymbolHandler, GetBarsHandler, etc.
- Trading handlers (4): ListOrdersHandler, GetOrderHandler, ListPositionsHandler, GetPositionHandler
- Strategy handlers (5): LoadStrategyHandler, StartStrategyHandler, StopStrategyHandler, GetOneHandler, GetAllHandler
- Backtesting handlers (5): RunBacktestHandler, OptimizeHandler, GetResultHandler, GetOptimizationHandler, ListResultsHandler

### Container Factory

**packages/pocketquant-api/src/pocketquant/api/di/container.py:**
- `PROVIDERS` list defines initialization order (CoreProvider → ... → HandlerProvider)
- `create_container()` - Returns AsyncContainer with all providers combined
- `register_handlers(container)` - Resolves all handlers, registers with Mediator

### Route Integration

```python
# Routes use FromDishka for injection (via setup_dishka)
from dishka.integrations.fastapi import FromDishka
from pocketquant.core.common.mediator import Mediator

@router.post("/sync")
async def sync_route(mediator: FromDishka[Mediator], command: SyncSymbolCommand):
    return await mediator.send(command)
```

## CQRS Flow

```
HTTP Request → Route (DishkaRoute + FromDishka[Mediator])
  ↓
Build Command/Query
  ↓
Mediator.send(request)
  ↓
Handler.handle() (from HandlerProvider)
  - Fetch: Infrastructure (TradingView, Database, Cache)
  - Validate: Domain layer (Bar.from_mongo())
  - Persist: Infrastructure (BarRepository.upsert_many())
  - Invalidate: Cache.delete_pattern()
  - Publish: EventBus.publish(event)
  ↓
Handler returns DTO (never entities)
  ↓
Route → HTTP Response (JSON)
```

## Data Pipelines

### Historical Data Pipeline

```
POST /market-data/sync
    ↓
SyncSymbolCommand → Mediator → SyncSymbolHandler
    ├─> TradingViewClient.fetch_ohlcv (thread pool)
    ├─> Domain validation via Bar.from_mongo()
    ├─> BarRepository.upsert_many() (MongoDB bulk_write)
    ├─> Cache.delete_pattern("bar:SYMBOL:*")
    └─> EventBus.publish(HistoricalDataSyncedEvent)
```

### Real-time Quote Pipeline

```
TradingView WebSocket → TradingViewWebSocketClient (binary frame parsing)
    ↓
QuoteAppService._on_quote_update
    ├─> Redis cache quote (60s TTL)
    ├─> BarAppService.process_tick (13 intervals: 1m-1M)
    │   ├─> Update OHLCV atomically (asyncio.Lock)
    │   ├─> Detect bar completion (time boundary)
    │   └─> _save_completed_bar()
    │       ├─> MongoDB: Bar.to_mongo()
    │       ├─> Redis: bar:current:{exchange}:{symbol}:{interval}
    │       └─> EventBus.publish(BarCompletedEvent)
    └─> EventBus.publish(QuoteReceivedEvent)
```

### Background Job Pipeline

```
APScheduler triggers job (6-hourly or market hours)
    ↓
sync_all_symbols job (each symbol independently)
    ├─> TradingViewClient.fetch_ohlcv
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
- In-memory with bounded history (**100 events**)
- No direct coupling between features

**Value Objects:** Immutable domain primitives
- Interval, OHLCV, BarRange, QuoteTick, Price, Signal
- Frozen dataclasses for immutability
- Validation in `__post_init__`
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
- StrategyAppService routes signals to broker

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
- AST parser checks for forbidden imports in `pocketquant.core.domain`
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
- `APP_PORT` - Host-mapped API port (default: **58921**, container always 41920)

## Dependencies

- **fastapi** - Web framework
- **pydantic** - Settings validation + Features layer (commands/queries). Domain layer uses stdlib dataclasses instead.
- **pymongo** - MongoDB driver (native async API, NOT Motor)
- **redis** - Async Redis client (redis-py)
- **structlog** - Structured logging
- **apscheduler** - Job scheduling (APScheduler)
- **tvdatafeed** - TradingView data source
- **aiohttp** - Async HTTP + WebSocket
- **pytest** - Testing framework
- **ruff** - Linting & formatting
- **pyright** - Type checking

## Entry Points

- **Development:** `just dev` (uvicorn on port 41920, local)
- **Production:** Docker compose with `APP_PORT` env var mapping to container port 41920
- **API Documentation:** `http://localhost:41920/api/v1/docs` (local dev)
- **Health Check:** `http://localhost:41920/health` (local dev)

## Recent Changes (2026-03-15)

**4-Package Monorepo Restructuring (2026-03-21)**
- Reorganized codebase: packages/{core, backtest, trading, api} using uv workspace
- Dependency graph enforced: core ← {backtest, trading} ← api
- Namespace packages (PEP 420): no __init__.py at pocketquant/ level

**DDD Aggregate Cleanup (2026-03-15)**
- `OHLCVRepository` → `BarRepository` (consistent naming)
- `SymbolAggregate` flattened to `Symbol` entity
- `OHLCVAggregate`, `QuoteAggregate` deleted (dead code)
- UUID7 time-ordered IDs throughout (B-tree friendly)

**CRITICAL: Domain Persistence Consolidation (2026-03-15)**
- `persistence/schemas/` directory DELETED
- All MongoDB persistence logic moved into domain entities (Pydantic BaseModel)
- Each aggregate now has `to_mongo()` → dict and `@classmethod from_mongo(doc)` → entity
- Repositories import directly from domain: `from pocketquant.core.domain.bar.entities import Bar`
- Result: Domain entities are now complete, self-contained units with built-in persistence

**Handler Extract-Method Pattern:**
- Complex handlers use private helpers (_fetch_bars, _persist_bars, _fail, _success, etc.)
- SyncSymbolHandler: 8 private helpers, GetOHLCVHandler: _build_cache_key, StopQuoteFeedHandler: _cancel_ws_task
- Guideline: Extract when handle() exceeds ~30 lines with 8+ operations

**Naming Standardization (2026-03-14):**
- DI providers consistently named (CoreProvider, PersistenceProvider, etc.)
- Application services standardized across layer
- Infrastructure clients follow unified naming pattern

**Dishka DI Migration (2026-03-13):**
- Replaced plain Python constructors + Services dataclass with dishka library
- Created 6 providers: CoreProvider, PersistenceProvider, InfrastructureProvider, MarketDataProvider, TradingProvider, HandlerProvider
- Lifespan now uses `create_container()` and `setup_dishka(container, app)` in pocketquant.api.main
- Routes use FromDishka[T] for injection
- Handler registration via `register_handlers(container)` in pocketquant.api.di.container

**Previous Changes (2026-02-14):**
- Clean Architecture Refactor Complete: Domain → Application → Features, Infrastructure ← Domain
- Persistence Layer Refactor: `pocketquant.core.persistence` package with 7 repositories
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
