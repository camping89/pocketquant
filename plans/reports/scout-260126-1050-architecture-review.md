# Scout Report: PocketQuant Architecture Review

**Date:** 2026-01-26 10:50  
**Scope:** Full codebase structure, vertical slice architecture, infrastructure patterns, naming conventions

---

## 1. Directory Structure Overview

```
src/
├── common/                    # Shared infrastructure (singletons)
│   ├── cache/
│   │   ├── __init__.py
│   │   └── redis_cache.py     # Cache singleton class
│   ├── database/
│   │   ├── __init__.py
│   │   └── connection.py      # Database singleton class (Motor async)
│   ├── jobs/
│   │   ├── __init__.py
│   │   └── scheduler.py       # JobScheduler singleton (APScheduler wrapper)
│   └── logging/
│       ├── __init__.py
│       └── setup.py           # Structured logging setup (structlog JSON)
│
├── features/
│   └── market_data/           # Single feature slice (currently)
│       ├── api/
│       │   ├── __init__.py
│       │   ├── routes.py      # Main FastAPI routes (sync, bulk sync, OHLCV queries)
│       │   └── quote_routes.py # Real-time quote WebSocket routes
│       ├── services/
│       │   ├── __init__.py
│       │   ├── data_sync_service.py      # Business logic for sync & cached retrieval
│       │   ├── quote_service.py          # WebSocket quote service (singleton pattern)
│       │   └── quote_aggregator.py       # Real-time tick aggregation into OHLCV bars
│       ├── repositories/
│       │   ├── __init__.py
│       │   ├── ohlcv_repository.py       # OHLCV & SyncStatus data access
│       │   └── symbol_repository.py      # Symbol metadata data access
│       ├── models/
│       │   ├── __init__.py
│       │   ├── ohlcv.py       # OHLCV, Interval enums, SyncStatus Pydantic models
│       │   ├── quote.py       # Quote, QuoteTick, AggregatedBar models
│       │   └── symbol.py      # Symbol, SymbolCreate models
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── tradingview.py         # TradingViewProvider (historical OHLCV)
│       │   └── tradingview_ws.py      # TradingViewWebSocketProvider (real-time ticks)
│       └── jobs/
│           ├── __init__.py
│           └── sync_jobs.py   # Background sync job definitions (6h interval + daily cron)
│
├── main.py                    # FastAPI app with lifespan manager
├── config.py                  # Pydantic Settings (from .env)
└── __init__.py
```

---

## 2. Key Files & Purposes

### Common Infrastructure (Singletons)

| File | Pattern | Purpose |
|------|---------|---------|
| `src/common/database/connection.py` | Class-based singleton | MongoDB async connection management via Motor |
| `src/common/cache/redis_cache.py` | Class-based singleton | Redis caching with JSON serialization & TTL support |
| `src/common/jobs/scheduler.py` | Class-based singleton | APScheduler wrapper for interval & cron jobs |
| `src/common/logging/setup.py` | Function-based | Structlog setup (JSON for prod, console for dev) |

### Feature Slice: market_data

**API Routes:**
- `routes.py`: Sync (single/bulk/background), OHLCV queries, symbol list, sync status endpoints
- `quote_routes.py`: Subscribe, unsubscribe, latest quote, all quotes, current bar, service start/stop/status

**Business Logic (Services):**
- `data_sync_service.py`: Orchestrates TradingView fetch → Repository upsert → cache invalidation
- `quote_service.py`: Global singleton managing WebSocket connection + subscription callbacks + aggregator integration
- `quote_aggregator.py`: Real-time tick aggregation into OHLCV bars across multiple intervals (1m, 5m, 1h, 1d)

**Data Access (Repositories):**
- `ohlcv_repository.py`: OHLCV & SyncStatus collections (bulk write, get bars, sync status tracking)
- `symbol_repository.py`: Symbol metadata collection (upsert, get, get_all, delete)

**External Integrations (Providers):**
- `tradingview.py`: Fetches historical OHLCV via tvdatafeed (runs in thread pool to avoid blocking)
- `tradingview_ws.py`: WebSocket connection to TradingView for real-time tick data

**Data Models (Pydantic):**
- `ohlcv.py`: OHLCV base/create/full models, Interval enum, SyncStatus, OHLCV↔Mongo conversion
- `quote.py`: Quote, QuoteTick, AggregatedBar models
- `symbol.py`: Symbol, SymbolCreate models

**Background Jobs:**
- `sync_jobs.py`: Registers 2 jobs: sync_all_symbols (6h interval), sync_daily_data (weekdays 9-17 cron)

---

## 3. Architecture Patterns

### 1. Vertical Slice Pattern
- ✅ FOLLOWED: Each feature (market_data) has its own complete stack: API → Services → Repositories → Models
- ✅ Self-contained: No cross-feature dependencies

### 2. Singleton Infrastructure
- ✅ CORRECTLY IMPLEMENTED:
  - `Database.connect()` in lifespan, then use `Database.get_collection()` anywhere
  - `Cache.connect()` in lifespan, then use `Cache.get()`, `Cache.set()` anywhere
  - `JobScheduler.initialize()` in lifespan, then use `JobScheduler.add_interval_job()` anywhere
  - Pattern: Class methods + class variables (`_client`, `_database`)

### 3. Repository Pattern
- ✅ CORRECTLY IMPLEMENTED:
  - All data access through `OHLCVRepository`, `SymbolRepository` (class-based static/class methods)
  - No raw MongoDB calls in services/routes
  - Async-first design with Motor
  - Bulk operations for efficiency (bulk_write in OHLCV)

### 4. Service Pattern
- ✅ CORRECTLY IMPLEMENTED:
  - Services instantiated with Settings (dependency injection)
  - `DataSyncService`: Stateful, instantiated per request, manages provider lifecycle
  - `QuoteService`: Global singleton via `get_quote_service()` factory function
  - Services contain business logic, not just data access

### 5. Provider Abstraction
- ✅ CORRECTLY IMPLEMENTED:
  - `TradingViewProvider`: Encapsulates tvdatafeed client + fetch logic (thread pooling for sync calls)
  - `TradingViewWebSocketProvider`: Encapsulates WebSocket connection + subscription management
  - Services depend on providers, not on external libs directly
  - Providers handle resource cleanup (`.close()` methods)

### 6. Structured Logging
- ✅ CORRECTLY IMPLEMENTED:
  - Structlog JSON format for production, console for dev
  - Event-based logging: `logger.info("event_name", key=value, ...)`
  - No string concatenation in logs
  - Used throughout infrastructure & services

---

## 4. Naming Conventions

### Services
- `DataSyncService` - ✅ Clear: sync-related business logic
- `QuoteService` - ✅ Clear: quote subscription + cache management
- `QuoteAggregator` - ✅ Clear: helper inside service, aggregates ticks

### Repositories
- `OHLCVRepository` - ✅ Clear: OHLCV + SyncStatus data access
- `SymbolRepository` - ✅ Clear: Symbol metadata

### Providers
- `TradingViewProvider` - ✅ Clear: external TradingView integration
- `TradingViewWebSocketProvider` - ✅ Clear: WebSocket variant

### Models
- `OHLCVCreate`, `OHLCV`, `OHLCVResponse` - ✅ Clear: input, storage, output
- `SymbolCreate`, `Symbol` - ✅ Clear: input, storage (no separate response)
- `Quote`, `QuoteTick`, `AggregatedBar` - ✅ Clear: domain models

### Infrastructure
- `Cache`, `Database`, `JobScheduler` - ✅ Clear: singleton pattern

---

## 5. Data Flow

### Historical Data Sync
```
API routes.sync()
  → DataSyncService.sync_symbol()
    → TradingViewProvider.fetch_ohlcv() (thread pool)
      → tvdatafeed client
    → OHLCVRepository.upsert_many() (bulk write)
    → SymbolRepository.upsert()
    → OHLCVRepository.update_sync_status()
    → Cache.delete_pattern() (invalidate cache)
```

### Real-time Quote Aggregation
```
WebSocket (TradingViewWebSocketProvider)
  → QuoteService._on_quote_update() (callback)
    → Cache.set() (latest quote)
    → QuoteAggregator.add_tick()
      → BarBuilder.add_tick()
      → [Bar complete] OHLCVRepository.upsert_many()
```

### Cached OHLCV Retrieval
```
API routes.get_ohlcv()
  → DataSyncService.get_cached_bars()
    → Cache.get() or OHLCVRepository.get_bars()
    → Cache.set() (5min TTL)
```

---

## 6. Architectural Strengths

1. **Clean Separation of Concerns**: API layer → Services → Repositories → Models
2. **Singleton Infrastructure**: Efficient resource management (single DB/cache/scheduler connection)
3. **Async-First Design**: Motor + asyncio throughout
4. **Provider Abstraction**: Easy to add new data providers (e.g., different exchange)
5. **Bulk Operations**: Efficient MongoDB batch writes
6. **Real-time + Historical**: Both WebSocket quotes + historical OHLCV in same codebase
7. **Background Jobs**: APScheduler integration for scheduled data sync
8. **Structured Logging**: Event-based, JSON-ready for production observability

---

## 7. Architectural Concerns & Minor Issues

### Minor Issues (Non-Critical)

1. **QuoteService Global Singleton via Factory Function**
   - Line: `src/features/market_data/services/quote_service.py:147-156`
   - Pattern: Global `_quote_service` variable with factory function
   - Risk: State shared across requests (by design, but could be confusing)
   - **Status**: Intentional for WebSocket lifecycle, document if needed

2. **Service `.close()` Method**
   - Lines: `src/features/market_data/api/routes.py:78, 97, 122, 154`
   - Pattern: Services have `.close()` for provider cleanup, called in finally blocks
   - Issue: Manual cleanup required; could be automated with context managers
   - **Status**: Works, but could be refactored to `async context manager` for safety

3. **Thread Pool Executor in Provider**
   - Line: `src/features/market_data/providers/tradingview.py:19`
   - Global `_executor = ThreadPoolExecutor(max_workers=4)`
   - Issue: Lifecycle not tied to app lifespan (no shutdown call)
   - **Status**: Minor; executor will be garbage collected on process exit

4. **Hard-Coded Interval Defaults**
   - Examples: `n_bars=5000`, `limit=1000`, `ttl=300` scattered throughout
   - Issue: No centralized config for these constants
   - **Status**: Minor; could extract to settings/constants

5. **No Input Validation in Repositories**
   - Repositories assume callers provide uppercase symbols
   - Issue: Could add validation for defensive programming
   - **Status**: Works with current usage (services handle), but could be hardened

### No Critical Architectural Issues Found

The codebase follows the Vertical Slice Architecture pattern very well. No fundamental structural problems.

---

## 8. Code Organization Recommendations

✅ **No changes needed** - Structure is solid.

If expanding to multiple features, next slice might be:
- `features/portfolio/` (user portfolios, positions)
- `features/backtesting/` (backtest engine)
- `features/alerts/` (price alerts, notifications)

---

## 9. Summary

| Aspect | Status | Details |
|--------|--------|---------|
| Vertical Slice Pattern | ✅ Excellent | Feature-complete, self-contained slices |
| Singleton Infrastructure | ✅ Excellent | Database, Cache, Scheduler properly initialized |
| Repository Pattern | ✅ Excellent | Class methods, async-first, bulk operations |
| Service Pattern | ✅ Excellent | Dependency injection, business logic separation |
| Provider Abstraction | ✅ Excellent | Clean external service interfaces |
| Error Handling | ✅ Good | Try/except in services, error status tracking |
| Logging | ✅ Excellent | Structured, event-based, production-ready |
| Naming | ✅ Excellent | Clear, descriptive, follows conventions |
| File Organization | ✅ Excellent | Logical grouping by concern |

**Overall Assessment**: Production-ready architecture with clean patterns and good separation of concerns.

---

## 10. Key Code Snippets

### Singleton Usage Pattern
```python
# In any service/route:
from src.common.database import Database
collection = Database.get_collection("ohlcv")
await collection.find_one(...)
```

### Service with Dependency Injection
```python
class DataSyncService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._tv_provider = TradingViewProvider(settings)
```

### Repository Class Methods
```python
class OHLCVRepository:
    @classmethod
    async def upsert_many(cls, records: list[OHLCVCreate]) -> int:
        collection = cls._get_collection()
        # bulk operations...
```

### Callback Pattern (Real-time)
```python
await self._provider.subscribe(
    symbol=symbol,
    exchange=exchange,
    callback=self._on_quote_update,
)
```

---

**Report Generated**: 2026-01-26 10:50  
**Reviewer**: Scout Agent
