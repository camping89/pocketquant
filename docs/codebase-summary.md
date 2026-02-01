# Codebase Summary

**Last Updated:** 2026-02-01 | **Codebase Size:** 12,420 LOC | **Python Files:** 180

## Architecture Overview

PocketQuant uses **DDD + CQRS + Vertical Slice Architecture** with strict layer separation:
- **Domain Layer:** Pure business logic (zero I/O)
- **Infrastructure Layer:** All external I/O (DB, cache, providers, scheduling)
- **Application Layer:** CQRS handlers + feature slices
- **Common Layer:** Mediator, EventBus, middleware, tracing

## Module Breakdown

### src/common (700 LOC, 28 files)

**Coordinators & Mediator:**
- **Mediator:** CQRS dispatcher, routes commands/queries to handlers
  - `register(request_type, handler)` - Register handler
  - `send(request)` - Dispatch to handler, raises HandlerNotFoundError if missing
- **EventBus:** In-memory async event bus (FIFO, 50 event max history)
  - `subscribe(event_type, handler)` - Register event subscriber
  - `publish(event)` - Notify all subscribers sequentially
  - `publish_all(events)` - Batch publish multiple events

**Tracing & Middleware:**
- **CorrelationIDMiddleware** - Inject correlation_id into context for request tracking
- **RequestLoggingMiddleware** - Log all requests/responses with correlation IDs
- `get_correlation_id()` - Access current correlation ID in async context
- **IdempotencyMiddleware** - Cache POST responses by idempotency_key header (24h TTL)
- **RateLimitMiddleware** - Token bucket (100 capacity, 10 tokens/sec refill) per IP

**Infrastructure Singletons:**
- **Database** - Async MongoDB singleton (Motor)
  - `get_collection(name)` - Access collection
  - `connect(settings)` - Initialize connection pool
  - `disconnect()` - Clean shutdown
- **Cache** - Async Redis singleton
  - `get(key)`, `set(key, value, ttl=None)`, `delete(key)`
  - `get_or_set(key, func, ttl)` - Cache-aside pattern
- **HealthCoordinator** - Parallel health checks (database, redis, jobs)
- **JobScheduler** - APScheduler wrapper (AsyncIOExecutor)

**Logging & Constants:**
- `setup_logging()` - structlog with JSON/console output
- `get_correlation_id()` - Thread/async-safe context variable access
- **constants.py** - Centralized cache keys, TTLs, limits, headers, interval mappings

### src/domain (1,674 LOC, 33 files)

**Aggregates (6):**
- **OHLCVAggregate** - Collection of OHLCV bars with validation
- **OrderAggregate** - Order lifecycle state machine
- **PositionAggregate** - Position tracking with P&L calculations
- **QuoteAggregate** - Quote with metadata
- **SymbolAggregate** - Symbol with exchange metadata
- **RiskConfigAggregate** - Risk parameters and position sizing

**Value Objects (Frozen Dataclasses):**
- **OHLCV** - (open, high, low, close, volume, timestamp)
- **BarRange** - (start_time, end_time) for bar alignment
- **PnL** - (unrealized, realized, total)
- **Signal** - Buy/sell signal with quantity
- **SymbolInfo** - (code, exchange, name, description)
- **Price** - Decimal price wrapper
- **QuoteTick** - Real-time price update
- **RiskConfig** - Risk model + parameters
- **Symbol** - (code, exchange) value object

**Enums:**
- **OrderType** - MARKET, LIMIT, STOP_LIMIT, STOP_MARKET
- **OrderSide** - BUY, SELL
- **OrderStatus** - PENDING, PARTIAL_FILL, FILLED, CANCELLED, REJECTED, ERROR (6 states with is_terminal, is_active)
- **PositionSide** - LONG, SHORT
- **Direction** - LONG, SHORT, EXIT, FLAT
- **RiskModel** - PERCENT_RISK, KELLY, FIXED
- **Interval** - 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M (13 timeframes)

**Domain Events (13+):**
- **OHLCV:** HistoricalDataSyncedEvent, BarCompletedEvent
- **Order:** OrderSubmittedEvent, OrderFilledEvent, OrderPartiallyFilledEvent, OrderCancelledEvent, OrderRejectedEvent
- **Position:** PositionOpenedEvent, PositionUpdatedEvent, PositionClosedEvent
- **Quote:** QuoteReceivedEvent, QuoteUpdatedEvent
- **Strategy:** SignalGeneratedEvent

**Domain Services:**
- **BarBuilder** - Incremental OHLCV bar construction from ticks
  - `add_tick(price, volume)` - Update bar with new tick
  - `is_complete()` - Check if bar period elapsed
  - `to_dict()` - Export bar as dict
- **PositionSizer** - Calculate position size by risk model
  - `calculate_size(account_balance, signal)` - Returns quantity
  - Supports: PERCENT_RISK, KELLY, FIXED

### src/infrastructure (3,127 LOC, 32 files)

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

**Persistence:**
- **Database** - MongoDB async wrapper (Motor)
  - Connection pooling
  - Async collection access
  - Transaction support
- **Cache** - Redis async wrapper
  - TTL-based expiration
  - JSON serialization
  - Key pattern deletion

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

### src/features (6,561 LOC, 85 files)

**backtesting/ (2,259 LOC)**
- **Routes:**
  - POST `/api/v1/backtest/run` - Execute backtest
  - POST `/api/v1/backtest/optimize` - Parameter optimization
  - GET `/api/v1/backtest/{run_id}` - Retrieve results
  - GET `/api/v1/backtest/{run_id}/equity` - Equity curve
  - GET `/api/v1/backtest/optimization/{id}` - Optimization results
  - GET `/api/v1/backtest/strategy/{id}` - Strategy results
- **Core Classes:**
  - **BacktestRunner** - Orchestrates backtest execution
  - **HistoricalReplayEngine** - Chronological bar replay
  - **GridOptimizer** - Parallel parameter search (multiprocessing)
  - **PerformanceCalculator** - Metrics (Sharpe, Sortino, max drawdown, win rate)
  - **BacktestResultCollector** - Aggregates results
  - **BacktestRepository** - MongoDB persistence

**market_data/ (2,116 LOC)**
- **Routes:**
  - POST `/api/v1/market-data/sync` - Single symbol sync (blocking)
  - POST `/api/v1/market-data/sync/background` - Async sync
  - POST `/api/v1/market-data/sync/bulk` - Multiple symbols
  - GET `/api/v1/market-data/ohlcv/{exchange}/{symbol}` - Query bars
  - GET `/api/v1/market-data/symbols` - List symbols
  - GET `/api/v1/market-data/sync-status` - Sync progress
  - POST `/api/v1/quotes/start` - Start WebSocket
  - POST `/api/v1/quotes/stop` - Stop WebSocket
  - GET `/api/v1/quotes/latest/{exchange}/{symbol}` - Latest quote
- **Core Classes:**
  - **BarManager** - Real-time multi-interval aggregation
  - **SyncSymbolHandler** - CQRS handler for sync
  - **BulkSyncHandler** - Batch sync handler
  - **GetOHLCVHandler** - Query handler
  - **GetSyncStatusHandler** - Status query
  - **StartQuoteFeedHandler**, **StopQuoteFeedHandler** - Quote management
  - **GetLatestQuoteHandler** - Quote retrieval

**strategy/ (1,236 LOC)**
- **Routes:**
  - GET `/api/v1/strategies` - List strategies
  - GET `/api/v1/strategies/{strategy_id}` - Get strategy details
  - POST `/api/v1/strategies/load` - Load strategy by name
  - POST `/api/v1/strategies/{id}/start` - Start strategy
  - POST `/api/v1/strategies/{id}/stop` - Stop strategy
- **Core Classes:**
  - **StrategyEngine** - Orchestrates strategy execution
  - **IStrategy** - ABC interface
    - `async on_bar(bar: OHLCVBar) → Optional[StrategySignal]`
    - `async on_tick(tick: QuoteTick) → Optional[StrategySignal]`
    - `async on_fill(order: Order) → None`
  - **StrategyLoader** - YAML loader
  - **LoadStrategyHandler**, **StartStrategyHandler**, **StopStrategyHandler** - CQRS handlers

**trading/ (782 LOC)**
- **Routes:**
  - GET `/api/v1/orders` - List orders
  - GET `/api/v1/orders/{order_id}` - Get order
  - GET `/api/v1/positions` - List positions
  - GET `/api/v1/positions/{strategy_id}` - Strategy positions
- **Core Classes:**
  - **OrderManager** - Order lifecycle
    - `async submit(symbol, side, type, quantity, price)`
    - `async cancel(order_id)`
    - `on_order_update(event)` - Event handler
  - **PositionTracker** - Subscribes to OrderFilledEvent
  - MongoDB persistence for orders and positions

**risk/ (163 LOC)**
- **Core Classes:**
  - **RiskCheckHandler** - Pre-trade validation
    - Check account balance
    - Validate position size
    - Check direction changes
    - Returns risk validation result

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
- **pydantic** - Settings + validation
- **motor** - Async MongoDB driver
- **redis** - Async Redis client
- **structlog** - Structured logging
- **apscheduler** - Job scheduling
- **tvdatafeed** - TradingView data source
- **aiohttp** - Async HTTP + WebSocket
- **pytest** - Testing framework

## Entry Points

- **Development:** `python -m src.main` (config via `.env`)
- **Production:** `python -m src.main` with `ENVIRONMENT=production`
- **API Documentation:** `http://localhost:$API_PORT/api/v1/docs`
- **Health Check:** `http://localhost:$API_PORT/health`

## Known Limitations

- In-memory EventBus (events lost on crash; use for non-critical events)
- In-memory job store (jobs lost on restart; reschedule on startup)
- No persistent outbox pattern (consider for mission-critical systems)
- Rate limiting state lost on Redis restart (acceptable for burst protection)
- Single-threaded strategy execution (one strategy per process)
- Domain purity enforced via AST check (cannot use I/O in domain/)
