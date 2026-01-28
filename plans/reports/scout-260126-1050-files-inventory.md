# Scout Report: Files Inventory & Quick Reference

**Date:** 2026-01-26  
**Purpose:** Quick lookup for all Python files organized by category

---

## Core Application Entry Points

| File | Purpose | Lines |
|------|---------|-------|
| `/Users/admin/workspace/_me/pocketquant/src/main.py` | FastAPI app factory + lifespan manager | 113 |
| `/Users/admin/workspace/_me/pocketquant/src/config.py` | Pydantic Settings from .env | 46 |

---

## Common Infrastructure (Singletons)

| File | Class | Methods | Purpose |
|------|-------|---------|---------|
| `/Users/admin/workspace/_me/pocketquant/src/common/database/connection.py` | `Database` | `connect()`, `disconnect()`, `get_database()`, `get_collection()` | MongoDB async connection via Motor |
| `/Users/admin/workspace/_me/pocketquant/src/common/cache/redis_cache.py` | `Cache` | `connect()`, `disconnect()`, `get()`, `set()`, `delete()`, `delete_pattern()`, `exists()`, `get_or_set()` | Redis caching with TTL |
| `/Users/admin/workspace/_me/pocketquant/src/common/jobs/scheduler.py` | `JobScheduler` | `initialize()`, `start()`, `shutdown()`, `add_interval_job()`, `add_cron_job()`, `remove_job()`, `get_jobs()`, `run_job_now()` | APScheduler wrapper |
| `/Users/admin/workspace/_me/pocketquant/src/common/logging/setup.py` | N/A | `setup_logging()`, `get_logger()` | Structlog JSON/console setup |

---

## Feature: market_data - API Routes

| File | Router Prefix | Endpoints | Purpose |
|------|---------------|-----------|---------|
| `/Users/admin/workspace/_me/pocketquant/src/features/market_data/api/routes.py` | `/market-data` | `/sync`, `/sync/background`, `/sync/bulk`, `/ohlcv/{exchange}/{symbol}`, `/symbols`, `/sync-status`, `/sync-status/{exchange}/{symbol}` | Historical data sync & OHLCV retrieval |
| `/Users/admin/workspace/_me/pocketquant/src/features/market_data/api/quote_routes.py` | `/quotes` | `/subscribe`, `/unsubscribe`, `/latest/{exchange}/{symbol}`, `/all`, `/current-bar/{exchange}/{symbol}`, `/start`, `/stop`, `/status` | Real-time quote WebSocket management |

---

## Feature: market_data - Services (Business Logic)

| File | Class | Methods | Purpose |
|------|-------|---------|---------|
| `/Users/admin/workspace/_me/pocketquant/src/features/market_data/services/data_sync_service.py` | `DataSyncService` | `sync_symbol()`, `sync_multiple_symbols()`, `get_cached_bars()`, `close()` | Orchestrates TradingView fetch → DB upsert → cache invalidation |
| `/Users/admin/workspace/_me/pocketquant/src/features/market_data/services/quote_service.py` | `QuoteService` | `start()`, `stop()`, `subscribe()`, `unsubscribe()`, `get_latest_quote()`, `get_all_quotes()`, `is_running()`, `get_aggregator()` | WebSocket quote service (global singleton) |
| `/Users/admin/workspace/_me/pocketquant/src/features/market_data/services/quote_aggregator.py` | `QuoteAggregator`, `BarBuilder` | `add_tick()`, `get_current_bar()`, `flush_all_bars()` | Real-time tick aggregation into OHLCV bars |

---

## Feature: market_data - Repositories (Data Access)

| File | Class | Methods | Collections | Purpose |
|------|-------|---------|-------------|---------|
| `/Users/admin/workspace/_me/pocketquant/src/features/market_data/repositories/ohlcv_repository.py` | `OHLCVRepository` | `upsert_many()`, `get_bars()`, `get_latest_bar()`, `get_bar_count()`, `update_sync_status()`, `get_sync_status()`, `get_all_sync_statuses()` | `ohlcv`, `sync_status` | OHLCV + sync status data access |
| `/Users/admin/workspace/_me/pocketquant/src/features/market_data/repositories/symbol_repository.py` | `SymbolRepository` | `upsert()`, `get()`, `get_all()`, `delete()` | `symbols` | Symbol metadata access |

---

## Feature: market_data - Providers (External Integrations)

| File | Class | Methods | Purpose |
|------|-------|---------|---------|
| `/Users/admin/workspace/_me/pocketquant/src/features/market_data/providers/tradingview.py` | `TradingViewProvider` | `fetch_ohlcv()`, `search_symbols()`, `close()` | Fetches historical OHLCV via tvdatafeed (thread pool) |
| `/Users/admin/workspace/_me/pocketquant/src/features/market_data/providers/tradingview_ws.py` | `TradingViewWebSocketProvider` | `connect()`, `disconnect()`, `subscribe()`, `unsubscribe()`, `run_forever()`, `is_connected()` | WebSocket real-time tick data |

---

## Feature: market_data - Models (Pydantic)

| File | Classes | Purpose |
|------|---------|---------|
| `/Users/admin/workspace/_me/pocketquant/src/features/market_data/models/ohlcv.py` | `Interval` (enum), `OHLCVCreate`, `OHLCV`, `OHLCVResponse`, `SyncStatus` | OHLCV & sync status models + Mongo converters |
| `/Users/admin/workspace/_me/pocketquant/src/features/market_data/models/quote.py` | `Quote`, `QuoteTick`, `AggregatedBar` | Real-time quote models |
| `/Users/admin/workspace/_me/pocketquant/src/features/market_data/models/symbol.py` | `SymbolCreate`, `Symbol` | Symbol metadata models |

---

## Feature: market_data - Background Jobs

| File | Functions | Trigger | Purpose |
|------|-----------|---------|---------|
| `/Users/admin/workspace/_me/pocketquant/src/features/market_data/jobs/sync_jobs.py` | `sync_all_symbols()`, `sync_daily_data()`, `register_sync_jobs()` | 6h interval, weekdays 9-17 | Automated data sync scheduling |

---

## MongoDB Collections

| Collection | Documents | Indexed By |
|------------|-----------|-----------|
| `ohlcv` | OHLCV bars | `symbol`, `exchange`, `interval`, `datetime` |
| `sync_status` | Sync status tracking | `symbol`, `exchange`, `interval` |
| `symbols` | Symbol metadata | `symbol`, `exchange` |

---

## Redis Cache Keys

| Pattern | TTL | Purpose |
|---------|-----|---------|
| `ohlcv:{symbol}:{exchange}:{interval}:*` | 5 min | Historical OHLCV queries |
| `quote:latest:{exchange}:{symbol}` | 60 sec | Latest quote cache |
| `quote:ticks:{exchange}:{symbol}` | dynamic | Tick buffer (not used) |
| `bar:current:{exchange}:{symbol}:{interval}` | 5 min | Current bar being built |

---

## Import Patterns

### Singleton Infrastructure Usage
```python
from src.common.database import Database
from src.common.cache import Cache
from src.common.jobs import JobScheduler
from src.common.logging import get_logger
```

### Feature Service Usage
```python
from src.features.market_data.services.data_sync_service import DataSyncService
from src.features.market_data.services.quote_service import get_quote_service
from src.features.market_data.repositories.ohlcv_repository import OHLCVRepository
from src.features.market_data.repositories.symbol_repository import SymbolRepository
```

### Model Usage
```python
from src.features.market_data.models.ohlcv import Interval, OHLCVCreate, OHLCV
from src.features.market_data.models.quote import Quote, QuoteTick
from src.features.market_data.models.symbol import Symbol, SymbolCreate
```

---

## File Statistics

- **Total Python files**: 32 (including __init__.py files)
- **Core application**: 2 files (main.py, config.py)
- **Common infrastructure**: 4 files (database, cache, jobs, logging)
- **Feature module files**: 26 files
  - API: 2 files
  - Services: 3 files
  - Repositories: 2 files
  - Providers: 2 files
  - Models: 3 files
  - Jobs: 1 file
  - __init__.py: 13 files

---

## Absolute File Paths Reference

### Application Entry
- `/Users/admin/workspace/_me/pocketquant/src/main.py`
- `/Users/admin/workspace/_me/pocketquant/src/config.py`

### Infrastructure
- `/Users/admin/workspace/_me/pocketquant/src/common/database/connection.py`
- `/Users/admin/workspace/_me/pocketquant/src/common/cache/redis_cache.py`
- `/Users/admin/workspace/_me/pocketquant/src/common/jobs/scheduler.py`
- `/Users/admin/workspace/_me/pocketquant/src/common/logging/setup.py`

### API Routes
- `/Users/admin/workspace/_me/pocketquant/src/features/market_data/api/routes.py`
- `/Users/admin/workspace/_me/pocketquant/src/features/market_data/api/quote_routes.py`

### Services
- `/Users/admin/workspace/_me/pocketquant/src/features/market_data/services/data_sync_service.py`
- `/Users/admin/workspace/_me/pocketquant/src/features/market_data/services/quote_service.py`
- `/Users/admin/workspace/_me/pocketquant/src/features/market_data/services/quote_aggregator.py`

### Repositories
- `/Users/admin/workspace/_me/pocketquant/src/features/market_data/repositories/ohlcv_repository.py`
- `/Users/admin/workspace/_me/pocketquant/src/features/market_data/repositories/symbol_repository.py`

### Providers
- `/Users/admin/workspace/_me/pocketquant/src/features/market_data/providers/tradingview.py`
- `/Users/admin/workspace/_me/pocketquant/src/features/market_data/providers/tradingview_ws.py`

### Models
- `/Users/admin/workspace/_me/pocketquant/src/features/market_data/models/ohlcv.py`
- `/Users/admin/workspace/_me/pocketquant/src/features/market_data/models/quote.py`
- `/Users/admin/workspace/_me/pocketquant/src/features/market_data/models/symbol.py`

### Jobs
- `/Users/admin/workspace/_me/pocketquant/src/features/market_data/jobs/sync_jobs.py`

