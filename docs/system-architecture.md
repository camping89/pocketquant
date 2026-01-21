# System Architecture

**Last Updated:** 2026-01-21

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    TradingView Data Source                       │
│              (REST API + WebSocket + Authentication)             │
└───────────────┬─────────────────────────────┬───────────────────┘
                │                             │
        Historical Data              Real-time Quotes
        (tvdatafeed)                 (Binary WebSocket)
                │                             │
                ▼                             ▼
    ┌───────────────────────┐    ┌───────────────────────┐
    │   FastAPI Endpoint    │    │   FastAPI Endpoint    │
    │   /market-data/sync   │    │   /quotes/subscribe   │
    └────────┬──────────────┘    └────────┬──────────────┘
             │                            │
             ▼                            ▼
    ┌──────────────────────────────────────────────┐
    │         Application Layer                    │
    │  ┌────────────────┐  ┌──────────────────┐   │
    │  │ DataSyncService│  │  QuoteService    │   │
    │  │ (per-request)  │  │  (singleton)     │   │
    │  └────────┬───────┘  └────────┬─────────┘   │
    │           │                   │              │
    │           │           ┌───────▼──────────┐   │
    │           │           │QuoteAggregator   │   │
    │           │           │(multi-interval)  │   │
    │           └───────┬───┴──────────────────┘   │
    └───────────────────┼──────────────────────────┘
                        │
           ┌────────────┴────────────┐
           │                         │
           ▼                         ▼
    ┌──────────────────┐   ┌──────────────────┐
    │   MongoDB        │   │   Redis Cache    │
    │ (OHLCV Storage)  │   │ (Quote + Bars)   │
    │ (Sync Status)    │   │ (300-3600s TTL)  │
    │ (Symbols)        │   │                  │
    └──────────────────┘   └──────────────────┘
             ▲                      ▲
             └──────────┬───────────┘
                        │
            ┌───────────▼──────────┐
            │  Infrastructure Layer │
            │ (Singleton Managers)  │
            └───────────────────────┘
```

## Infrastructure Singletons

### Pattern: Class-Method Based Singletons

All infrastructure components use class methods as their API. State is maintained in class variables and initialized once during app startup in the lifespan context manager.

```python
# Usage pattern
from src.common.database import Database
from src.common.cache import Cache

# Direct access via class methods
collection = Database.get_collection("ohlcv")
await Cache.set("key", {"data": "value"})
```

### Database (PyMongo Async + MongoDB)

**Initialization (in main.py lifespan):**
```python
await Database.connect(settings)
```

**State:**
- `_client: pymongo.asynchronous.AsyncMongoClient` - MongoDB connection
- `_database: pymongo.asynchronous.AsyncDatabase` - Default database reference
- Connection pool: 5-50 connections (configurable)

**Lifecycle:**
- Connected once at startup
- Single connection shared across all requests
- Gracefully disconnected at shutdown

**API Methods:**
- `connect(settings)` - Initialize connection
- `disconnect()` - Close connection
- `get_database(name=None)` - Get database reference
- `get_collection(name)` - Get collection reference
- `ping()` - Test connectivity

**Collections:**
- `ohlcv` - Time-series market data (indexed by symbol, exchange, interval, timestamp)
- `sync_status` - Synchronization progress tracking
- `symbols` - Symbol registry with metadata

### Cache (redis-py)

**Initialization:**
```python
await Cache.connect(settings)
```

**State:**
- `_pool: aioredis.Redis` - Redis connection pool
- JSON serialization/deserialization with date handling
- Default TTL: 3600s (configurable per operation)

**Lifecycle:**
- Single connection at startup (redis-py handles pooling internally)
- Graceful disconnect at shutdown
- Automatic reconnection on transient failures

**API Methods:**
- `connect(settings)` - Initialize connection
- `disconnect()` - Close connection
- `get(key)` - Retrieve and deserialize
- `set(key, value, ttl=3600)` - Serialize and cache
- `delete(key)` - Remove single key
- `delete_pattern(pattern)` - SCAN-based pattern deletion (for invalidation)
- `exists(key)` - Check existence
- `get_or_set(key, factory, ttl=3600)` - Atomic get-or-compute

**Cache Layers:**
- `quote:latest:{EXCHANGE}:{SYMBOL}` (60s) - Latest market quote
- `bar:current:{EXCHANGE}:{SYMBOL}:{interval}` (300s) - In-progress OHLCV bar
- `ohlcv:{SYMBOL}:{EXCHANGE}:{interval}:{limit}` (300s) - Historical query results

### Logging (structlog)

**Initialization (in main.py):**
```python
setup_logging(settings)
```

**Pipeline (processors):**
1. `contextvars.get("request_id")` - Add request correlation ID
2. Log level filtering
3. Logger name mapping
4. Timestamp generation
5. Exception traceback formatting
6. Application context (environment, version)

**Output Formats:**
- **Production (LOG_FORMAT=json):** Single-line JSON for log aggregation
- **Development (LOG_FORMAT=console):** Pretty-printed console output

**Compatible Sinks:** Datadog, Splunk, ELK, CloudWatch, Google Cloud Logging, Grafana Loki

### Job Scheduler (APScheduler)

**Initialization (in main.py):**
```python
JobScheduler.initialize(settings)
JobScheduler.start()
```

**Configuration:**
- **Executor:** AsyncIOExecutor (runs on event loop)
- **Job Store:** MemoryJobStore (in-memory, non-persistent)
- **Job Coalescing:** True (skip missed runs)
- **Max Instances:** 3 (prevent overlapping job execution)
- **Grace Time:** 60s (wait for graceful shutdown)

**Lifecycle:**
- Initialized and started at startup
- Gracefully shutdown with `wait=True` (wait for running jobs)
- In-memory storage acceptable for non-critical sync jobs

**Scheduled Jobs:**
- `sync_all_symbols` - Every 6 hours (500 bars per symbol)
- `sync_daily_data` - Hourly Mon-Fri 9-17 UTC (10 bars, daily interval)

## Data Pipelines

### Pipeline 1: Historical Data Synchronization

```
API Request (POST /market-data/sync)
    │
    ▼
DataSyncService.sync_symbol()
    │
    ├─> Update sync_status → "pending"
    │
    ├─> TradingViewProvider (thread pool)
    │   ├─> Lazy client init
    │   ├─> Fetch bars (max 5000)
    │   └─> Return OHLCV records
    │
    ├─> OHLCVRepository.upsert_many()
    │   ├─> Bulk insert/update (MongoDB)
    │   └─> Unique key: (symbol, exchange, interval, timestamp)
    │
    ├─> Update sync_status → "completed"
    │
    └─> Cache.delete_pattern("ohlcv:{symbol}:*")
        └─> Invalidate all cached queries
```

**Status Tracking:**
- Initial: `pending` (request received)
- Running: `syncing` (data fetch in progress)
- Final: `completed` (success) or `error` (with error_message)

**Error Handling:**
- Catches all exceptions
- Updates sync_status with error details
- Returns error response without re-raising

### Pipeline 2: Real-time Quote Processing

```
WebSocket Frame (Binary Protocol)
    │
    ▼
TradingViewWebSocketProvider
    ├─> Parse frame: ~m~{length}~m~{json}
    ├─> Validate message format
    └─> Emit to subscribers
        │
        ▼
QuoteService._on_quote_update()
    ├─> Cache latest quote → Redis (60s TTL)
    ├─> Log quote event
    └─> Feed to QuoteAggregator
        │
        ▼
QuoteAggregator.process_tick()
    ├─> For each configured interval
    │   ├─> Get/create BarBuilder
    │   ├─> Update OHLCV fields atomically (asyncio.Lock)
    │   └─> Check if bar complete (time boundary crossed)
    │
    ├─> On bar completion
    │   ├─> Save to MongoDB (OHLCV collection)
    │   ├─> Update current bar in Redis
    │   └─> Log bar completed
    │
    └─> On process stop
        └─> flush_all_bars()
            ├─> Save incomplete bars
            └─> Prevent data loss
```

**Time Alignment:**
- Daily bars: Midnight UTC boundary
- Intraday bars: Epoch-aligned (UNIX timestamp % interval_seconds == 0)

**Concurrency:**
- asyncio.Lock per aggregator (thread-safe bar building)
- No race conditions between tick processing and bar saves

### Pipeline 3: Background Job Execution

```
APScheduler (startup)
    │
    ▼
JobScheduler.start() + register_sync_jobs()
    │
    ├─> add_interval_job(sync_all_symbols, 6 hours)
    │   └─> Every 6 hours
    │       └─> For each symbol
    │           └─> sync_symbol(symbol, exchange, "1d", n_bars=500)
    │
    └─> add_cron_job(sync_daily_data, 9-17 UTC Mon-Fri)
        └─> Hourly 9-17 UTC Mon-Fri
            └─> For each symbol
                └─> sync_symbol(symbol, exchange, "1d", n_bars=10)
```

**Error Isolation:**
- Per-symbol errors don't break loop
- Failed symbols logged, loop continues
- Status updates reflect individual symbol state

## Concurrency Model

### Event Loop (Main Thread)

FastAPI/Uvicorn runs async code on single event loop. All I/O awaited properly:

```python
# Correct: async/await
await Database.get_collection("x").find_one()
await Cache.set("key", value)
```

### Thread Pool (I/O Isolation)

Blocking I/O (TradingView tvdatafeed library) runs in ThreadPoolExecutor:

```python
# TradingViewProvider
executor = ThreadPoolExecutor(max_workers=4)
bars = await loop.run_in_executor(executor, client.get_bars, symbol)
```

**Why:**
- tvdatafeed is blocking (no async support)
- Running in thread pool prevents event loop blocking
- Max 4 workers limit prevents resource exhaustion
- Each request gets timeout protection

### Asyncio.Lock (Aggregator)

QuoteAggregator uses asyncio.Lock for thread-safe bar building:

```python
async with self._lock:
    bar_builder.update_ohlc(tick)
```

**Why:**
- Multiple ticks may arrive while saving previous bar
- Lock ensures atomic read-modify-write
- No data corruption or race conditions

## Resource Lifecycle

### Startup Sequence (main.py lifespan)

```python
async with contextmanager(app):
    # Initialize in order
    settings = get_settings()
    setup_logging(settings)
    await Database.connect(settings)  # MongoDB
    await Cache.connect(settings)      # Redis
    JobScheduler.initialize(settings)  # APScheduler
    JobScheduler.start()               # Start scheduling
    register_sync_jobs()               # Register sync tasks

    yield  # Serve requests

    # Cleanup in reverse order
    JobScheduler.shutdown(wait=True)
    await Cache.disconnect()
    await Database.disconnect()
```

### Connection Pooling

- **MongoDB:** 5-50 connections (configurable min/max)
- **Redis:** Internal connection pooling (redis-py handles)
- **Thread Pool:** 4 workers for blocking I/O

### Graceful Shutdown

1. JobScheduler.shutdown(wait=True) - Wait for running jobs
2. Cache.disconnect() - Flush pending operations
3. Database.disconnect() - Close all connections
4. Uvicorn gracefully stops accepting new requests

**Grace Period:** 60s (configured in JobScheduler)

## Integration Points

### TradingView REST API

- **Library:** tvdatafeed
- **Authentication:** Optional username/password
- **Rate Limiting:** None explicitly (TradingView limits internally)
- **Max Bars:** 5000 per request
- **Executor:** ThreadPoolExecutor isolation

### TradingView WebSocket

- **Protocol:** Binary frames: ~m~{length}~m~{json}
- **Endpoint:** wss://data.tradingview.com/socket.io/websocket
- **Message Types:** Quote updates, heartbeat pings
- **Reconnection:** Exponential backoff (1s → 60s)
- **Re-subscription:** Automatic after reconnect

### MongoDB

- **Driver:** PyMongo (native async API)
- **Operations:** Async I/O, bulk upserts, aggregation pipelines
- **Indexes:** Created manually or via init script
- **TTL:** Not used (cache invalidation via pattern matching)

### Redis

- **Driver:** redis-py (async)
- **Serialization:** JSON with custom date handling
- **TTL:** 60s (quotes), 300s (bars/queries)
- **Persistence:** Not used (ephemeral cache only)

## Error Handling Strategy

### Transient Errors (Retryable)

- Database connection timeouts
- Redis connection failures
- TradingView API temporary unavailability

**Handling:** Exponential backoff, auto-reconnect, update status → "error"

### Permanent Errors (Non-retryable)

- Invalid symbol or exchange
- Authentication failure
- Malformed API response

**Handling:** Update status → "error" with message, log, return to client

### Silent Failures (Logged, No Status)

- Job execution errors (logged but not exposed via status)
- Cache invalidation failures (data continues to exist)

**Handling:** Structured logging, monitoring via log aggregation

## Production Considerations

### Infrastructure Monitoring

- [ ] Database connectivity health check (/health endpoint)
- [ ] Redis connectivity health check
- [ ] Job execution metrics (failed/succeeded counts)
- [ ] WebSocket connection uptime
- [ ] Cache hit/miss ratios

### Scaling Strategies

**Horizontal (multiple workers):**
```bash
# Workers configured via uvicorn; port/host via .env
uvicorn src.main:app --workers 4
```
- Each worker has independent singletons
- Shared MongoDB/Redis across workers
- Job scheduler must handle distributed execution (currently in-memory only)

**Vertical (single worker optimization):**
- Tune MongoDB connection pool (min/max)
- Adjust ThreadPoolExecutor workers (currently 4)
- Optimize Redis batch operations

### Observability

**Logging:**
- All events logged as JSON (production-ready)
- Compatible with Datadog, Splunk, ELK, CloudWatch

**Metrics Needed:**
- Sync success/failure rates per symbol
- WebSocket uptime/reconnect count
- Cache hit rates
- Database query latency
- Job execution time

### Security

- TradingView credentials in environment variables (never committed)
- MongoDB authentication via DSN
- Redis authentication via DSN
- CORS configuration available (not default-open)

## Performance Characteristics

### Latency

- **Historical Sync:** 1-5s per 5000 bars (network + DB write)
- **WebSocket Quote:** <100ms from TradingView to client
- **Bar Aggregation:** <1ms per tick (in-memory processing)
- **Cache Lookup:** <5ms (Redis)

### Throughput

- **Concurrent Syncs:** Limited by ThreadPoolExecutor (4 workers)
- **Quote Subscriptions:** Limited by WebSocket frame handling (1000+ ticks/sec)
- **Database:** Depends on MongoDB capacity (bulk upserts optimized)

### Memory

- **MongoDB Pool:** ~10-20MB per connection
- **Redis Pool:** <1MB
- **In-memory Jobs:** <10MB (scheduler + job store)
- **Aggregator State:** ~10MB per 10k subscriptions
