# System Architecture

**Last Updated:** 2026-02-13 | **Version:** 1.0 | **Status:** Production-Ready | **Pattern:** Operation-First Vertical Slices

## High-Level Architecture

PocketQuant uses **DDD + CQRS + Vertical Slice Architecture** with strict layer separation.

```
┌─────────────────────────────────────────────────────────────────┐
│                         External Services                        │
│              TradingView (REST API + WebSocket)                  │
└───────────────┬─────────────────────────────┬───────────────────┘
                │                             │
        Historical Data              Real-time Quotes
                │                             │
                ▼                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       API Layer (FastAPI)                        │
│  POST /market-data/sync   GET /market-data/ohlcv   /quotes/*    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Middleware Stack (Ordered)                     │
│  CorrelationId → RateLimit → Idempotency → Routes               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CQRS Mediator (Dispatcher)                    │
│  send(Command/Query) → Handler → Response                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
┌───────────────────────┐       ┌───────────────────────┐
│  Application Layer    │       │    Domain Layer       │
│  (CQRS Handlers)      │◄──────│  (Pure Logic)         │
│  - SyncHandler        │       │  - OHLCVAggregate     │
│  - OHLCVHandler       │       │  - Symbol             │
│  - QuoteHandler       │       │  - Interval           │
└───────┬───────────────┘       └───────────────────────┘
        │                                 │
        │         ┌───────────────────────┘
        │         │
        ▼         ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Infrastructure Layer (I/O)                       │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │  Persistence  │  │  Providers   │  │   Scheduling     │    │
│  │  - MongoDB    │  │  - TradingVw │  │   - APScheduler  │    │
│  │  - Redis      │  │  - HTTP      │  │   - Jobs         │    │
│  └───────────────┘  └──────────────┘  └──────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│   MongoDB    │  │  TradingView │  │   Background     │
│   (Bars)     │  │   (Market)   │  │   Jobs           │
└──────────────┘  └──────────────┘  └──────────────────┘
```

## DDD Layer Architecture

### Layer 1: Domain (Pure Business Logic)

**Purpose:** Core business rules with ZERO external dependencies.

**Rules:**
- No I/O imports (no pymongo, redis, aiohttp)
- Immutable value objects (frozen dataclasses)
- Domain events for state changes
- Validated via __post_init__

**Components:**
```
domain/
├── ohlcv/
│   ├── aggregate.py      # OHLCVAggregate (collection validation)
│   ├── value_objects.py  # OHLCVBar (immutable)
│   ├── events.py         # BarSyncedEvent
│   └── services/         # Domain services (pure logic)
├── quote/
│   ├── aggregate.py      # QuoteAggregate
│   ├── value_objects.py  # QuoteTick
│   └── events.py         # QuoteReceivedEvent
├── symbol/
│   ├── aggregate.py      # Symbol aggregate
│   └── value_objects.py  # Symbol value object
└── shared/
    ├── value_objects.py  # Symbol, Interval, INTERVAL_SECONDS
    └── events.py         # DomainEvent base class
```

**Example Value Object:**
```python
@dataclass(frozen=True)
class Symbol:
    code: str
    exchange: str

    def __post_init__(self) -> None:
        if not self.code or not self.exchange:
            raise ValueError("Symbol requires code and exchange")
```

**Enforcement:** `test_domain_purity.py` uses AST parsing to detect forbidden imports.

### Layer 2: Application (CQRS Handlers, Operation-First)

**Purpose:** Orchestrate domain + infrastructure to fulfill use cases. Each operation is a self-contained use case.

**Pattern:** Command/Query handlers registered with Mediator. Each operation folder contains its complete logic.

**Structure (Operation-First Vertical Slice):**
```
features/market_data/
├── base/                        # Shared infrastructure within feature
│   ├── jobs/                    # Background job definitions
│   ├── managers/                # Stateful services (BarManager)
│   ├── models/                  # Pydantic DTOs shared by multiple operations
│   ├── providers/               # External integrations (TradingViewProvider)
│   └── services/                # Business logic (DataSyncService)
├── sync/                        # Nested feature: Data synchronization
│   ├── sync_one/                # Operation: Sync single symbol
│   │   ├── command.py           # SyncSymbolCommand
│   │   ├── handler.py           # SyncSymbolHandler
│   │   └── route.py             # Route: POST /market-data/sync
│   ├── sync_bulk/               # Operation: Sync multiple symbols
│   │   ├── command.py           # BulkSyncCommand
│   │   ├── handler.py           # BulkSyncHandler
│   │   └── route.py             # Route: POST /market-data/sync/bulk
│   ├── dto.py                   # DTOs shared by sync operations
│   └── router.py                # Sync sub-router (imports sync_one, sync_bulk routes)
├── ohlcv/                       # Nested feature: OHLCV queries
│   ├── get_ohlcv/               # Operation: Get bars
│   │   ├── query.py             # GetOHLCVQuery
│   │   ├── handler.py           # GetOHLCVHandler
│   │   └── route.py             # Route: GET /market-data/ohlcv/{exchange}/{symbol}
│   └── router.py
├── quotes/                      # Nested feature: Quote management
│   ├── start_feed/              # Operation: Start WebSocket
│   │   ├── command.py
│   │   ├── handler.py
│   │   └── route.py
│   ├── stop_feed/               # Operation: Stop WebSocket
│   │   ├── command.py
│   │   ├── handler.py
│   │   └── route.py
│   ├── subscribe/               # Operation: Subscribe symbol
│   │   ├── command.py
│   │   ├── handler.py
│   │   └── route.py
│   ├── get_all/                 # Operation: Get all quotes
│   │   ├── query.py
│   │   ├── handler.py
│   │   └── route.py
│   ├── get_latest/              # Operation: Get latest quote
│   │   ├── query.py
│   │   ├── handler.py
│   │   └── route.py
│   └── router.py
├── status/                      # Nested feature: Status queries
│   ├── get_sync_status/         # Operation: Get sync status
│   │   ├── query.py
│   │   └── handler.py
│   ├── get_quote_service_status/# Operation: Get quote feed status
│   │   ├── query.py
│   │   └── handler.py
│   └── router.py
├── list_symbols/                # Standalone operation
│   ├── query.py                 # ListSymbolsQuery
│   ├── handler.py               # ListSymbolsHandler
│   └── route.py                 # Route: GET /market-data/symbols
├── repositories/                # Data access layer (shared)
│   ├── ohlcv_repository.py
│   ├── symbol_repository.py
│   └── sync_status_repository.py
├── router.py                    # Main feature router
└── __init__.py
```

**Operation Structure (Inside an operation folder):**
```
operation_name/
├── command.py           # Command definition + validation (mutating operations)
│   # class {Action}Command(BaseModel): ...
├── query.py             # Query definition + validation (read-only operations)
│   # class Get{Resource}Query(BaseModel): ...
├── handler.py           # CQRS handler (always present)
│   # class {Action}Handler(Handler[{Command/Query}, {Response}]):
│   #     async def handle(self, request: {Command/Query}) -> {Response}: ...
├── route.py             # FastAPI route (optional, not always needed)
│   # @router.post("/...") async def route(...): ...
└── __init__.py
```

**Handler Responsibilities:** Receive Command/Query → Fetch from Infrastructure → Execute Domain logic → Persist → Publish DomainEvents → Return DTO

**Example:** `backtesting/run/` contains `command.py` (RunBacktestCommand), `handler.py` (RunBacktestHandler), `route.py` (POST /run). Handler loads strategy, fetches historical bars, runs BacktestRunner, calculates metrics, persists to MongoDB, returns result DTO.

### Layer 3: Infrastructure (External I/O)

**Purpose:** All external integrations (DB, cache, HTTP, WebSocket, scheduling).

**Structure:**
```
infrastructure/
├── persistence/
│   ├── mongodb.py        # MongoDBConnection wrapper
│   └── redis.py          # RedisConnection wrapper
├── tradingview/
│   ├── provider.py       # REST API (tvdatafeed + ThreadPoolExecutor)
│   ├── websocket.py      # Binary WebSocket protocol
│   └── base.py           # IDataProvider interface
├── scheduling/
│   └── scheduler.py      # APScheduler wrapper
├── http_client/
│   └── client.py         # Generic HTTP client (aiohttp)
└── webhooks/
    └── dispatcher.py     # Webhook notifications
```

**Key Services:**
- **MongoDBConnection:** Async collection access (PyMongo)
- **RedisConnection:** JSON serialization + TTL support
- **TradingViewProvider:** ThreadPoolExecutor for blocking I/O
- **TradingViewWebSocketProvider:** Binary frame parsing and quote streaming
- **JobScheduler:** APScheduler (in-memory, non-persistent)

### Layer 4: Common (Cross-Cutting)

**Purpose:** Mediator, EventBus, middleware, tracing, health, UUID utilities.

**Structure:**
```
common/
├── mediator/
│   ├── mediator.py       # CQRS dispatcher
│   ├── handler.py        # Handler[TRequest, TResponse] base
│   └── exceptions.py     # HandlerNotFoundError
├── messaging/
│   ├── event_bus.py      # In-memory async event bus
│   ├── event_handler.py  # EventHandler base
│   ├── event_registry.py # @event_handler decorator + auto-discovery
│   └── event_registry.py # EventRegistry for scanning & binding handlers
├── tracing/
│   ├── correlation.py    # Correlation ID management
│   └── context.py        # ContextVar storage
├── health/
│   ├── coordinator.py    # Health aggregation
│   └── checks.py         # DB/Cache/Jobs health checks
├── idempotency/
│   └── middleware.py     # IdempotencyMiddleware (24h TTL)
├── rate_limit/
│   └── middleware.py     # RateLimitMiddleware (200 req/10s)
├── uuid.py               # UUID7 generation (time-ordered IDs)
├── database/             # Singleton wrappers (legacy, in common for now)
├── cache/
├── logging/
└── jobs/
```

## CQRS Flow

### Request Flow (Commands)

```
1. HTTP Request
   POST /market-data/sync
   Body: {symbol, exchange, interval, n_bars}

2. Middleware Stack
   CorrelationIdMiddleware → inject correlation_id
   RateLimitMiddleware → check token bucket
   IdempotencyMiddleware → check cache (if idempotency_key)

3. Route Handler
   - Parse request body
   - Build SyncSymbolCommand
   - Call Mediator.send(command)

4. Mediator Dispatch
   - Lookup handler for SyncSymbolCommand
   - Call handler.handle(command)

5. Handler Execution
   - Fetch from TradingViewProvider (infrastructure)
   - Validate via OHLCVAggregate (domain)
   - Save to MongoDB (infrastructure)
   - Invalidate Redis cache (infrastructure)
   - Publish BarSyncedEvent (event bus)
   - Return SyncResultDTO

6. Route Response
   - Convert DTO to JSON
   - Return HTTP 200 with body
```

### Request Flow (Queries)

```
1. HTTP Request
   GET /market-data/ohlcv/{exchange}/{symbol}?interval=1d&limit=100

2. Middleware Stack
   CorrelationIdMiddleware → inject correlation_id
   RateLimitMiddleware → check token bucket
   (No idempotency for GET requests)

3. Route Handler
   - Parse query params
   - Build GetBarsQuery
   - Call Mediator.send(query)

4. Mediator Dispatch
   - Lookup handler for GetBarsQuery
   - Call handler.handle(query)

5. Handler Execution
   - Check Redis cache (infrastructure)
   - If miss: Query MongoDB (infrastructure)
   - Cache result in Redis (infrastructure)
   - Map to OHLCVBar value objects (domain)
   - Return BarsDTO

6. Route Response
   - Convert DTO to JSON
   - Return HTTP 200 with body
```

## Trading Persistence Layer

### MongoDB Collections

**Orders Collection (`orders`):**
- Persists all order lifecycle events (submitted, filled, partial, cancelled, rejected)
- Documents indexed by: `_id` (order_id), `strategy_id`, `status`, `(symbol, exchange)`
- `OrderRepository.save()` - Upsert order state
- `OrderRepository.find_pending()` - Recover orders in non-terminal states on startup
- All order state changes persisted immediately (submit, fill, cancel, reject)

**Positions Collection (`positions`):**
- Tracks per-strategy open and closed positions with P&L
- Documents indexed by: `_id` (position_id), `strategy_id`, `is_closed`, `(symbol, exchange)`
- `PositionRepository.save()` - Upsert position state
- `PositionRepository.find_open()` - Recover open positions on startup
- Position created on first OrderFilledEvent, updated on subsequent fills, closed when quantity reaches 0

### Recovery on Startup

```
Application Startup
  ↓
OrderRepository.ensure_indexes() - Create MongoDB indexes
PositionRepository.ensure_indexes()
  ↓
OrderManager.load_pending_orders()
  └─> Load orders with status: pending, submitted, partially_filled
      └─> Restore in-memory state + broker_order_id mapping
  ↓
PositionTracker.start()
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

### IBroker Interface

All brokers implement consistent contract:

```python
class IBroker(ABC):
    async def submit_order(self, order: Order) -> ExecutionResult
    async def cancel_order(self, order_id: str) -> bool
    async def get_positions(self) -> List[Position]
    async def get_orders(self) -> List[Order]
```

### PaperBroker (Simulation)

In-memory execution without real trades:
- Configurable slippage (% or fixed points)
- Configurable fill delay (milliseconds)
- Position tracking with entry/exit prices
- P&L calculations
- No external dependencies

**Use case:** Backtesting, paper trading, development

### OKXBroker (Live Trading)

Live execution via OKX Exchange:
- HMAC-SHA256 authentication
- WebSocket connection to OKX
- Exponential backoff reconnection (1s → 30s max, 10-failure circuit breaker)
- State reconciliation on reconnect
- Order submission → fill handling → position update
- Real-time market data from OKX

**Configuration:**
- OKX_API_KEY: API key
- OKX_SECRET_KEY: Secret key
- OKX_PASSPHRASE: API passphrase

**Reconnection Strategy:**
```
Initial failure → 1s delay
2nd failure → 2s delay
4th failure → 4s delay
...
Max 30s delay
10 failures → 5-min pause (circuit breaker)
```

## Middleware Stack

**Execution Order:** Request flows through middleware in registration order.

```
Request
  ↓
CorrelationIdMiddleware
  - Generate/extract correlation_id
  - Set in ContextVar for logging
  ↓
RateLimitMiddleware
  - Check token bucket (200 req/10s per IP)
  - Reject if exceeded (429 Too Many Requests)
  ↓
IdempotencyMiddleware
  - Check idempotency_key header (POST only)
  - Return cached response if duplicate
  ↓
Route Handler
  - Execute business logic via Mediator
  ↓
Response
```

**Configuration:**
```python
# main.py
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(RateLimitMiddleware, capacity=200, refill_rate=20)
app.add_middleware(IdempotencyMiddleware, ttl_seconds=86400)
```

## Event Bus Pattern

**Purpose:** Decouple features via domain events.

**Flow:**
```
Handler publishes event
  ↓
EventBus.publish(event)
  ↓
For each subscriber:
  - Call handler(event)
  - Await if coroutine
  ↓
Store in history (deque, max 50)
```

**Example:**
```python
# In SyncSymbolHandler
await self.event_bus.publish(BarSyncedEvent(
    symbol=symbol,
    exchange=exchange,
    bars_count=len(bars)
))

# In event_handlers.py
async def on_bar_synced(event: BarSyncedEvent) -> None:
    logger.info("bars_synced", symbol=event.symbol, count=event.bars_count)

# Register subscriber
event_bus.subscribe(BarSyncedEvent, on_bar_synced)
```

**Characteristics:**
- In-memory (no persistence)
- FIFO delivery order
- Bounded history (50 events)
- Sync + async handlers supported

## Data Pipelines

### Historical Data Sync Pipeline

```
POST /market-data/sync
  ↓
Route → SyncSymbolCommand → Mediator
  ↓
SyncSymbolHandler
  ├─> TradingViewProvider.fetch_ohlcv
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
TradingViewWebSocketProvider.parse_frame
  ↓
QuoteService._on_quote_update
  ├─> Redis.set(f"quote:latest:{exchange}:{symbol}", quote, ttl=60)
  │
  ├─> BarManager.process_tick(quote)
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
StrategyEngine._on_market_event
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
      ├─> PositionTracker._on_order_filled
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
  ├─> BacktestRunner.run()
  │   ├─> Initialize PaperBroker
  │   ├─> Initialize StrategyEngine
  │   │
  │   └─> For each bar (chronological):
  │       ├─> Inject bar to StrategyEngine
  │       ├─> Strategy.on_bar(bar) → signal
  │       ├─> RiskCheckHandler.check_signal()
  │       ├─> PaperBroker.submit_order()
  │       ├─> Simulate fill with slippage/delay
  │       ├─> Update PositionTracker
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
  ├─> GridOptimizer.optimize()
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

TradingView REST API (tvdatafeed) is blocking:

```python
# TradingViewProvider
executor = ThreadPoolExecutor(max_workers=4)
bars = await loop.run_in_executor(executor, client.get_hist, ...)
```

**Why:**
- tvdatafeed has no async support
- Thread pool prevents event loop blocking
- Max 4 workers = limit concurrent blocking calls

### Asyncio.Lock (Quote Aggregation)

BarManager uses lock for thread-safe bar building:

```python
async with self._lock:
    bar_builder.update_ohlc(tick)
    if bar_complete:
        await self._save_bar(bar_builder.build())
```

**Why:**
- Multiple ticks may arrive while saving bar
- Lock ensures atomic read-modify-write
- No race conditions or data corruption

## Resource Lifecycle

### Startup Sequence

1. `get_settings()` + `setup_logging()`
2. `Database.connect()` → `Cache.connect()` → `JobScheduler.start()`
3. Create `Mediator` + `EventBus`, register all CQRS handlers
4. `register_sync_jobs()` for background scheduling
5. `yield` → serve requests

### Graceful Shutdown

1. Stop accepting new requests (Uvicorn)
2. `strategy_engine.stop()` → `JobScheduler.shutdown(wait=True)`
3. `Cache.disconnect()` → `Database.disconnect()`

## Integration Points

### TradingView REST API

- **Library:** tvdatafeed
- **Auth:** Optional username/password
- **Max bars:** 5000 per request
- **Isolation:** ThreadPoolExecutor (max 4 workers)
- **Timeout:** Per-request timeout protection

### TradingView WebSocket

- **Protocol:** Binary frames (~m~{length}~m~{json})
- **Endpoint:** wss://data.tradingview.com/socket.io/websocket
- **Reconnection:** Exponential backoff (1s → 60s max)
- **Re-subscription:** Automatic after reconnect
- **Heartbeat:** Ping/pong handling

### OKX WebSocket

- **Protocol:** JSON messages (native WebSocket)
- **Endpoint:** wss://ws.okx.com:8443/ws/v5/public (public), /private (authenticated)
- **Authentication:** HMAC-SHA256 signature (timestamp + body)
- **Reconnection:** Exponential backoff (1s → 30s max, 10-failure circuit breaker)
- **Heartbeat:** Server pings every 30s, client must pong
- **Subscriptions:** Position updates, order updates, trade fills
- **State Sync:** On reconnect, fetch current orders/positions from REST API

### MongoDB

- **Driver:** PyMongo (native async API)
- **Pool:** 5-50 connections (configurable)
- **Operations:** Bulk upserts, aggregation pipelines
- **Collections:** ohlcv, sync_status, symbols

### Redis

- **Driver:** redis-py (async)
- **Serialization:** JSON with custom date handling
- **TTL:** 60s (quotes), 300s (bars/queries), 86400s (idempotency)
- **Patterns:** SCAN for pattern-based deletion

## Error Handling

### Transient Errors (Retryable)

- Database connection timeouts → Auto-reconnect
- Redis connection failures → Auto-reconnect
- TradingView API temporary unavailable → Exponential backoff

### Permanent Errors (Non-retryable)

- Invalid symbol/exchange → Return 400 Bad Request
- Authentication failure → Return 401 Unauthorized
- Handler not found → Return 500 Internal Server Error

### Silent Failures (Logged Only)

- Background job failures → Logged, next run continues
- Cache invalidation failures → Logged, data stale but functional
- Event subscriber errors → Logged, other subscribers continue

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
| Memory (BarManager) | ~10MB per 10k subscriptions |

## Security

- **Credentials:** Environment variables only (never committed)
- **Auth:** MongoDB/Redis via DSN (username/password)
- **Rate Limiting:** IP-based (200 req/10s)
- **Idempotency:** Prevent duplicate requests (24h TTL)
