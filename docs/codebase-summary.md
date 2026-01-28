# Codebase Summary

**Last Updated:** 2026-01-28 | **Codebase Size:** ~4,200 LOC | **Python Files:** 65

## Architecture Overview

PocketQuant uses **DDD + CQRS + Vertical Slice Architecture** with strict layer separation:
- **Domain Layer:** Pure business logic (zero I/O)
- **Infrastructure Layer:** All external I/O (DB, cache, providers, scheduling)
- **Application Layer:** CQRS handlers + feature slices
- **Common Layer:** Mediator, EventBus, middleware, tracing

```
src/
├── common/              # CQRS + utilities (~800 LOC)
│   ├── constants.py     # Centralized constants
│   ├── mediator/        # CQRS Mediator (request dispatch)
│   ├── messaging/       # In-memory EventBus
│   ├── tracing/         # Correlation ID + context
│   ├── health/          # Health coordinator
│   ├── idempotency/     # Idempotency middleware
│   ├── rate_limit/      # Rate limiting middleware
│   ├── database/        # Database singleton (moved to infrastructure mentally)
│   ├── cache/           # Cache singleton (moved to infrastructure mentally)
│   ├── logging/         # Structured logging
│   └── jobs/            # Scheduler singleton (moved to infrastructure mentally)
│
├── domain/              # PURE business logic (~600 LOC, ZERO I/O)
│   ├── ohlcv/           # OHLCV aggregate + entities + value objects + events
│   ├── quote/           # Quote aggregate + events
│   ├── symbol/          # Symbol aggregate + value objects
│   └── shared/          # Shared value objects (Symbol, Interval) + base events
│
├── infrastructure/      # ALL external I/O (~900 LOC)
│   ├── persistence/     # MongoDB + Redis wrappers
│   ├── scheduling/      # APScheduler wrapper
│   ├── tradingview/     # TradingView REST + WebSocket providers
│   ├── http_client/     # HTTP client abstraction
│   └── webhooks/        # Webhook dispatcher
│
├── features/market_data/  # Application Layer (~1,800 LOC)
│   ├── sync/            # Command: SyncSymbol (historical data)
│   ├── ohlcv/           # Query: GetBars, GetSymbols
│   ├── quote/           # Command: Start/Stop/Subscribe WebSocket
│   ├── status/          # Query: GetSyncStatus, GetQuoteStatus
│   ├── api/             # FastAPI routes (dispatch to Mediator)
│   ├── jobs/            # Background sync jobs
│   ├── models/          # Legacy models (being deprecated)
│   ├── managers/        # BarManager (quote aggregation)
│   └── services/        # Legacy services (being deprecated)
│
└── main.py              # FastAPI app + lifespan + middleware stack
```

## Layer Responsibilities

### Common Layer (Coordinators + Mediator)

**Mediator:** Routes commands/queries to handlers
- `register(request_type, handler)` - Register handler
- `send(request)` - Dispatch to handler

**EventBus:** In-memory async event bus (FIFO)
- `subscribe(event_type, handler)` - Register listener
- `publish(event)` - Notify all subscribers
- `publish_all(events)` - Batch publish
- Max 50 event history (bounded deque)

**Tracing:** Correlation ID for request tracking
- `CorrelationIdMiddleware` - Inject correlation_id
- `get_correlation_id()` - Access current correlation_id

**Health:** Dependency health checks
- `HealthCoordinator` - Aggregate health from DB, Cache, Jobs
- `/health` endpoint - JSON status + dependencies

**Idempotency:** Prevent duplicate POST requests
- `IdempotencyMiddleware` - Cache responses by idempotency_key
- 24h TTL on cached responses

**Rate Limiting:** Token bucket rate limiting
- `RateLimitMiddleware` - 200 req/10s per IP
- Redis-backed distributed rate limiting

### Domain Layer (Pure Business Logic)

**OHLCV:**
- `OHLCVBar` - Value object (open, high, low, close, volume, timestamp)
- `OHLCVAggregate` - Bar collection with validation
- `BarSyncedEvent` - Domain event when bars saved

**Quote:**
- `QuoteTick` - Real-time price update value object
- `QuoteAggregate` - Quote with metadata
- `QuoteReceivedEvent` - Domain event on new quote

**Symbol:**
- `Symbol(code, exchange)` - Value object (frozen dataclass)
- `Symbol.from_string("NASDAQ:AAPL")` - Parse helper
- Validation: requires non-empty code + exchange

**Shared:**
- `Interval` - Enum (1m, 5m, 15m, 1h, 4h, 1d, 1w, 1M)
- `INTERVAL_SECONDS` - Mapping to seconds
- `DomainEvent` - Base class (event_id, occurred_at)

### Infrastructure Layer (External I/O)

**Persistence:**
- `MongoDBConnection` - Async MongoDB client wrapper
- `RedisConnection` - Async Redis client wrapper
- Direct collection access for handlers (no repository pattern)

**TradingView:**
- `TradingViewProvider` - REST API (tvdatafeed, ThreadPoolExecutor)
- `TradingViewWebSocketProvider` - Binary WebSocket protocol
- `IDataProvider` - Abstract interface for providers

**Scheduling:**
- `JobScheduler` - APScheduler wrapper (AsyncIOExecutor)
- In-memory job store (non-persistent)
- Coalesce=True (skip missed runs)

**HTTP Client:**
- Generic async HTTP client wrapper (aiohttp)

**Webhooks:**
- Webhook dispatcher for external notifications

### Application Layer (CQRS Handlers)

**Sync Feature (Commands):**
- `SyncSymbolCommand` - Fetch historical bars
- `SyncSymbolHandler` - Orchestrates: Provider → Domain → DB → Events

**OHLCV Feature (Queries):**
- `GetBarsQuery` - Retrieve historical bars
- `GetSymbolsQuery` - List tracked symbols
- Handlers fetch directly from MongoDB

**Quote Feature (Commands):**
- `StartQuoteStreamCommand` - Start WebSocket
- `StopQuoteStreamCommand` - Stop WebSocket
- `SubscribeQuoteCommand` - Register for symbol updates
- Handlers manage QuoteService singleton

**Status Feature (Queries):**
- `GetSyncStatusQuery` - Sync job status
- `GetQuoteStatusQuery` - WebSocket connection status

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

## Middleware Stack (Execution Order)

```
Request → CorrelationIdMiddleware → RateLimitMiddleware → IdempotencyMiddleware → Route
```

1. **CorrelationIdMiddleware:** Inject correlation_id into context
2. **RateLimitMiddleware:** Check token bucket (200 req/10s per IP)
3. **IdempotencyMiddleware:** Check cache for duplicate requests (POST only)
4. **Route:** Execute business logic via Mediator

## Data Pipelines

### Historical Data Pipeline

```
POST /market-data/sync
    ↓
SyncSymbolCommand → Mediator
    ↓
SyncSymbolHandler
    ├─> TradingViewProvider.fetch_ohlcv (thread pool)
    ├─> Domain validation via OHLCVAggregate
    ├─> MongoDB bulk_write (upsert)
    ├─> Redis cache invalidation (pattern delete)
    └─> EventBus.publish(BarSyncedEvent)
```

### Real-time Quote Pipeline

```
TradingView WebSocket → Binary Frame
    ↓
TradingViewWebSocketProvider.parse_frame
    ↓
QuoteService._on_quote_update
    ├─> Redis cache (60s TTL)
    ├─> BarManager.process_tick (multi-interval aggregation)
    │   ├─> Build OHLCV bars (1m, 5m, 15m, etc.)
    │   └─> On bar complete → MongoDB save
    └─> EventBus.publish(QuoteReceivedEvent)
```

## Key Patterns

**Mediator Pattern:** Single entry point for all requests
- Decouples routes from handlers
- Easy to add middleware/logging/tracing
- Testable in isolation

**Event Bus Pattern:** Decoupled domain events
- Handlers publish events, subscribers react
- No direct coupling between features
- In-memory (no persistence overhead)

**Value Objects:** Immutable domain primitives
- Symbol, Interval, OHLCVBar, QuoteTick
- Frozen dataclasses for immutability
- Validation in __post_init__

**CQRS:** Commands vs Queries separation
- Commands: mutate state, return DTO
- Queries: read-only, return DTO
- No shared models between command/query

## Configuration

All settings via environment variables (`.env` file):
- `MONGODB_URL` - MongoDB DSN
- `REDIS_URL` - Redis DSN
- `LOG_FORMAT` - "json" (prod) or "console" (dev)
- `LOG_LEVEL` - log level (debug, info, warning, error)
- `TRADINGVIEW_USERNAME` - Optional TradingView auth
- `TRADINGVIEW_PASSWORD` - Optional TradingView auth
- `ENVIRONMENT` - "development" or "production"

## Testing Strategy

**Unit Tests:**
- `tests/unit/common/` - Mediator, EventBus
- `tests/unit/domain/` - Value objects, aggregates, purity check
- `tests/unit/features/` - Handler tests with mocks

**Domain Purity Test:**
- AST parser checks for forbidden imports in `src/domain/`
- Forbidden: pymongo, redis, aiohttp, src.infrastructure, src.common.database
- Ensures domain layer has zero I/O dependencies

**Integration Tests:**
- `tests/integration/` - Route tests with real DB/Cache (future)

## Dependencies

- **fastapi** - Web framework
- **pymongo** - MongoDB driver (async)
- **redis** - Async Redis client
- **structlog** - Structured logging
- **pydantic** - Settings + validation
- **apscheduler** - Job scheduling
- **tvdatafeed** - TradingView data source
- **aiohttp** - Async HTTP + WebSocket
- **pytest** - Testing

## Entry Points

- **Development:** `python -m src.main` (config via `.env`)
- **Production:** `python -m src.main` with `ENVIRONMENT=production`
- **Documentation:** `http://localhost:$API_PORT/api/v1/docs`
- **Health Check:** `http://localhost:$API_PORT/health`

## Migration Status

**Completed:**
- ✅ Constants centralized
- ✅ Infrastructure layer extracted
- ✅ Domain layer created (pure, zero I/O)
- ✅ Mediator + EventBus implemented
- ✅ Features refactored to CQRS
- ✅ Middleware stack integrated
- ✅ Health + idempotency + rate limiting + tracing

**Deprecated (to be removed):**
- `features/market_data/repositories/` - Direct DB access in handlers now
- `features/market_data/services/` - Replaced by CQRS handlers

## Known Limitations

- In-memory EventBus (events lost on crash)
- In-memory job store (jobs lost on restart)
- No persistent outbox pattern
- WebSocket reconnection requires resubscription
- Rate limiting state lost on Redis restart
