# System Architecture

**Last Updated:** 2026-01-28

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

### Layer 2: Application (CQRS Handlers)

**Purpose:** Orchestrate domain + infrastructure to fulfill use cases.

**Pattern:** Command/Query handlers registered with Mediator.

**Structure:**
```
features/market_data/
├── sync/
│   ├── command.py        # SyncSymbolCommand
│   ├── handler.py        # SyncSymbolHandler
│   ├── dto.py            # Response DTOs
│   └── event_handlers.py # EventBus subscribers
├── ohlcv/
│   ├── query.py          # GetBarsQuery, GetSymbolsQuery
│   ├── handler.py        # Query handlers
│   └── dto.py            # Response DTOs
├── quote/
│   ├── command.py        # Start/Stop/Subscribe commands
│   ├── handler.py        # Command handlers
│   └── dto.py            # Response DTOs
└── status/
    ├── query.py          # GetSyncStatusQuery
    ├── handler.py        # Query handler
    └── dto.py            # Response DTOs
```

**Handler Responsibilities:**
1. Receive Command/Query from Mediator
2. Fetch data from Infrastructure
3. Execute domain logic via Domain layer
4. Persist results via Infrastructure
5. Publish DomainEvents to EventBus
6. Return DTO

**Example Handler:**
```python
class SyncSymbolHandler(Handler[SyncSymbolCommand, SyncResultDTO]):
    def __init__(self, provider: IDataProvider, event_bus: EventBus):
        self.provider = provider
        self.event_bus = event_bus

    async def handle(self, cmd: SyncSymbolCommand) -> SyncResultDTO:
        # 1. Fetch from infrastructure
        bars = await self.provider.fetch_ohlcv(...)

        # 2. Domain validation
        aggregate = OHLCVAggregate(bars)

        # 3. Persist via infrastructure
        await Database.get_collection("ohlcv").insert_many(...)

        # 4. Publish events
        await self.event_bus.publish(BarSyncedEvent(...))

        # 5. Return DTO
        return SyncResultDTO(bars_synced=len(bars))
```

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
- **TradingViewWebSocketProvider:** Binary frame parsing (~m~{len}~m~{json})
- **JobScheduler:** APScheduler (in-memory, non-persistent)

### Layer 4: Common (Cross-Cutting)

**Purpose:** Mediator, EventBus, middleware, tracing, health.

**Structure:**
```
common/
├── mediator/
│   ├── mediator.py       # CQRS dispatcher
│   ├── handler.py        # Handler[TRequest, TResponse] base
│   └── exceptions.py     # HandlerNotFoundError
├── messaging/
│   ├── event_bus.py      # In-memory async event bus
│   └── event_handler.py  # EventHandler base
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

```python
async with asynccontextmanager(app):
    # Initialize in order
    settings = get_settings()
    setup_logging(settings)

    # Infrastructure
    await Database.connect(settings)
    await Cache.connect(settings)
    JobScheduler.initialize(settings)
    JobScheduler.start()

    # Register handlers
    mediator = Mediator()
    event_bus = EventBus()

    # Register CQRS handlers
    mediator.register(SyncSymbolCommand, SyncSymbolHandler(...))
    mediator.register(GetBarsQuery, GetBarsHandler(...))

    # Register event subscribers
    event_bus.subscribe(BarSyncedEvent, on_bar_synced)

    # Register background jobs
    register_sync_jobs()

    yield  # Serve requests

    # Cleanup in reverse order
    JobScheduler.shutdown(wait=True)
    await Cache.disconnect()
    await Database.disconnect()
```

### Graceful Shutdown

1. Stop accepting new requests (Uvicorn)
2. JobScheduler.shutdown(wait=True) - Wait 60s for running jobs
3. Cache.disconnect() - Flush pending operations
4. Database.disconnect() - Close all connections

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

### Latency

- **Historical Sync:** 1-5s per 5000 bars (network + DB write)
- **WebSocket Quote:** <100ms from TradingView to handler
- **Bar Aggregation:** <1ms per tick (in-memory)
- **Cache Lookup:** <5ms (Redis)
- **Mediator Dispatch:** <0.1ms (dict lookup)

### Throughput

- **Concurrent Syncs:** Limited by ThreadPoolExecutor (4 workers)
- **Quote Subscriptions:** 1000+ ticks/sec (WebSocket + asyncio)
- **Database:** Depends on MongoDB capacity (bulk upserts optimized)
- **Rate Limit:** 200 req/10s per IP (configurable)

### Memory

- **MongoDB Pool:** ~10-20MB per connection
- **Redis Pool:** <1MB
- **EventBus History:** ~1KB per 50 events
- **Mediator Registry:** <1KB
- **BarManager State:** ~10MB per 10k subscriptions

## Security

- **Credentials:** Environment variables only (never committed)
- **MongoDB Auth:** Via DSN (username/password)
- **Redis Auth:** Via DSN (optional password)
- **Rate Limiting:** IP-based (200 req/10s)
- **Idempotency:** Prevent duplicate requests (24h TTL)
- **CORS:** Configurable (not default-open)
