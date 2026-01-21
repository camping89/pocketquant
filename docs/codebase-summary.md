# Codebase Summary

**Last Updated:** 2026-01-21 | **Codebase Size:** ~3,600 LOC | **Python Files:** 33

## Architecture Overview

PocketQuant uses **Vertical Slice Architecture** where each feature is self-contained with its own API, services, repositories, models, and jobs. Shared infrastructure (Database, Cache, Logging, Jobs) is organized in `common/` as class-based singletons accessed via class methods.

```
src/
├── common/              # Shared infrastructure (964 LOC)
│   ├── database/        # MongoDB (PyMongo async API)
│   ├── cache/           # Redis abstraction (JSON serialization)
│   ├── logging/         # Structured JSON logging (structlog)
│   └── jobs/            # APScheduler wrapper
│
├── features/            # Feature slices
│   └── market_data/     # Market data feature (2,714 LOC)
│       ├── api/         # FastAPI routes (472 LOC)
│       ├── services/    # Business logic (848 LOC)
│       ├── repositories/ # Data access (428 LOC)
│       ├── models/      # Pydantic models (289 LOC)
│       ├── providers/   # TradingView integrations (572 LOC)
│       └── jobs/        # Scheduled sync (118 LOC)
│
├── main.py              # FastAPI app entry point
└── config.py            # Pydantic Settings
```

## Core Infrastructure (964 LOC)

### Database (src/common/database/)
- **Driver:** PyMongo (native async API)
- **Pattern:** Class-based singleton
- **Connection Pool:** 5-50 (configurable)
- **Lifecycle:** Initialized in app startup, connection maintained across requests
- **API:** `Database.get_collection(name)` for direct collection access

### Cache (src/common/cache/)
- **Driver:** redis-py (async)
- **Serialization:** Auto JSON serialization/deserialization with date handling
- **TTL:** 3600s default (configurable per operation)
- **Lifecycle:** Single connection initialized at startup
- **API:** `Cache.get()`, `Cache.set()`, `Cache.delete()`, `Cache.delete_pattern()`
- **Advanced:** `get_or_set()` for atomic operations, SCAN for pattern-based deletion

### Logging (src/common/logging/)
- **Library:** structlog with JSON output
- **Modes:** JSON for production, console for development
- **Context:** Thread-local storage for request tracing
- **Processors:** Context vars, log level, logger name, timestamp, exception details, app context
- **Compatible:** Datadog, Splunk, ELK, CloudWatch, Google Cloud Logging, Grafana Loki

### Jobs (src/common/jobs/)
- **Library:** APScheduler with AsyncIOScheduler
- **Storage:** In-memory MemoryJobStore (non-persistent)
- **Execution:** AsyncIOExecutor on event loop
- **Defaults:** coalesce=True (skip missed runs), max_instances=3, grace_time=60s
- **API:** `add_interval_job()`, `add_cron_job()`, `remove_job()`, `get_jobs()`

## Startup Sequence

```
get_settings() (cached)
    ↓
setup_logging(settings)
    ↓
await Database.connect(settings)
    ↓
await Cache.connect(settings)
    ↓
JobScheduler.initialize(settings)
    ↓
JobScheduler.start()
    ↓
register_sync_jobs()
    ↓
[serve requests]
    ↓
[graceful shutdown]
    ↓
JobScheduler.shutdown(wait=True)
    ↓
await Cache.disconnect()
    ↓
await Database.disconnect()
```

## Market Data Feature (2,714 LOC)

Two independent pipelines:

### Historical Data Pipeline
- **Source:** TradingView REST API (tvdatafeed library)
- **Thread Pool:** ThreadPoolExecutor (max 4 workers) to isolate blocking I/O
- **Constraints:** 5000 bar maximum per fetch
- **Storage:** MongoDB (OHLCV collection)
- **Caching:** Pattern-based deletion after sync
- **Sync Types:** Manual, background, bulk with status tracking

### Real-time Quotes Pipeline
- **Source:** TradingView WebSocket (wss://data.tradingview.com/socket.io/websocket)
- **Protocol:** Binary framing ~m~{length}~m~{json}
- **Reconnection:** Exponential backoff (1s to 60s)
- **Processing:** QuoteService (singleton) → QuoteAggregator → OHLCV bars
- **Storage:** Redis (60s TTL) + MongoDB for completed bars
- **Intervals:** 1m, 5m, 15m, 1h, 4h, 1d, 1w, 1M

## Repositories (428 LOC)

### OHLCVRepository
- All class methods (stateless design)
- Collections: `ohlcv`, `sync_status`
- Key methods: `upsert_many()` (bulk operations), `get_bars()` (filtered queries), `update_sync_status()`

### SymbolRepository
- CRUD operations for symbol tracking
- Collection: `symbols`

## Services (848 LOC)

### DataSyncService (244 LOC)
- **Pattern:** Per-request instantiation with Settings injection
- **Status Flow:** pending → syncing → completed/error
- **Behavior:** Fetches from TradingView, upserts to MongoDB, invalidates cache
- **Error Handling:** Captures errors, updates status, returns error details

### QuoteService (236 LOC)
- **Pattern:** Global singleton for WebSocket persistence
- **Lifecycle Management:** `start()`, `stop()`, callbacks
- **Caching:** Quotes cached in Redis (60s TTL)
- **Health Check:** Verifies both internal `_running` flag and provider connection state

### QuoteAggregator (368 LOC)
- **Purpose:** Convert real-time ticks into OHLCV bars at multiple intervals
- **Concurrency:** asyncio.Lock for thread-safe bar building
- **Time Alignment:** Midnight UTC for daily bars, epoch-aligned for intraday
- **Cleanup:** `flush_all_bars()` saves incomplete bars on shutdown

## Models (289 LOC)

- **Interval:** 13 timeframes (1m to 1M) enumeration
- **OHLCV/OHLCVCreate:** Time-series bar data with creation models
- **Quote/QuoteTick:** Latest quotes and tick events
- **AggregatedBar:** In-progress bar container
- **Symbol/SymbolBase:** Symbol tracking with metadata

## Providers (572 LOC)

### TradingViewProvider (217 LOC)
- Wraps tvdatafeed library
- ThreadPoolExecutor isolation (max 4 concurrent)
- Lazy client initialization with optional authentication
- 5000 bar limit enforced per fetch

### TradingViewWebSocketProvider (355 LOC)
- Binary protocol handling with frame parsing
- Message format: ~m~{length}~m~{json}
- Auto-reconnect with exponential backoff
- Re-subscription after reconnection
- Heartbeat ping/pong handling

## API Routes (472 LOC)

### market_data/routes.py
- POST `/market-data/sync` - Single symbol sync (blocking)
- POST `/market-data/sync/background` - Async sync
- POST `/market-data/sync/bulk` - Multiple symbols
- GET `/market-data/ohlcv/{exchange}/{symbol}` - Historical data
- GET `/market-data/symbols` - Tracked symbols
- GET `/market-data/sync-status` - Sync progress

### market_data/quote_routes.py
- POST `/quotes/start` - Start WebSocket
- POST `/quotes/stop` - Stop WebSocket
- POST `/quotes/subscribe` - Register for updates
- POST `/quotes/unsubscribe` - Unregister
- GET `/quotes/latest/{exchange}/{symbol}` - Latest quote
- GET `/quotes/all` - All cached quotes
- GET `/quotes/current-bar/{exchange}/{symbol}` - In-progress bar
- GET `/quotes/status` - Connection status

## Caching Strategy (Redis TTLs)

- `quote:latest:{EXCHANGE}:{SYMBOL}` (60s) - Latest quote cache
- `bar:current:{EXCHANGE}:{SYMBOL}:{interval}` (300s) - In-progress bars
- `ohlcv:{SYMBOL}:{EXCHANGE}:{interval}:{limit}` (300s) - Historical data queries

Invalidation: Pattern-based deletion after sync + automatic expiration.

## Background Jobs

- **sync_all_symbols** - Every 6 hours (500 bars per symbol)
- **sync_daily_data** - Hourly Mon-Fri 9-17 UTC (10 bars, daily interval only)
- Registered at startup, persisted in-memory only (non-critical data)

## Key Design Decisions

1. **Singleton Singletons vs DI:** Expensive connections (DB, Cache) are singletons to avoid overhead. Infrastructure accessed directly via class methods rather than FastAPI Depends() to simplify service layer.

2. **Service Patterns:** DataSyncService instantiated per-request (stateless), QuoteService is global singleton (WebSocket state must persist).

3. **Thread Pool Isolation:** TradingView blocking I/O runs in ThreadPoolExecutor to avoid blocking async event loop.

4. **In-Memory Jobs:** Sync jobs are non-critical and acceptable to lose on restart. Reduces dependencies (no Celery/RabbitMQ needed).

5. **Pattern-Based Cache Invalidation:** After sync, entire cache patterns deleted to ensure freshness. No selective invalidation complexity.

6. **Binary WebSocket Protocol:** TradingView uses custom frame format requiring manual parsing. No standard WebSocket library can decode automatically.

## Configuration

All settings via environment variables (`.env` file):
- `MONGODB_URL` - MongoDB DSN
- `REDIS_URL` - Redis DSN
- `LOG_FORMAT` - "json" (prod) or "console" (dev)
- `LOG_LEVEL` - log level (debug, info, warning, error)
- `TRADINGVIEW_USERNAME` - Optional TradingView auth
- `TRADINGVIEW_PASSWORD` - Optional TradingView auth
- `ENVIRONMENT` - "development" or "production"

## Dependencies

- **fastapi** - Web framework
- **pymongo** - MongoDB driver (native async API)
- **redis** - Async Redis client
- **structlog** - Structured logging
- **pydantic** - Settings and validation
- **apscheduler** - Job scheduling
- **tvdatafeed** - TradingView data source
- **aiohttp** - Async HTTP client (WebSocket support)
- **pytest** - Testing

## Entry Points

- **Development:** `python -m src.main` (config via `.env`)
- **Production:** `python -m src.main` with `ENVIRONMENT=production`
- **Documentation:** `http://localhost:$API_PORT/api/v1/docs`
- **Health Check:** `http://localhost:$API_PORT/health`

## TODOs & Known Limitations

- [ ] Automatic reconnection retry if MongoDB/Redis disconnects
- [ ] Persistent job storage (currently in-memory only)
- [ ] Infrastructure observability (health checks for DB/Cache connectivity)
- [ ] Singleton mocking in tests (test utilities)
- [ ] Bulk sync parallelization (currently sequential)
- [ ] Symbol search implementation
- [ ] Rate limiting on TradingView requests
- [ ] Configurable aggregator intervals post-initialization
