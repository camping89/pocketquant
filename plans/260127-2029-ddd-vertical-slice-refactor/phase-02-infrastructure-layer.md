# Phase 2: Infrastructure Layer

## Context Links
- Parent: [plan.md](plan.md)
- Dependencies: None (can run parallel with Phase 1)
- Research: [DDD Patterns](research/researcher-ddd-cqrs-patterns.md)

## Overview

| Field | Value |
|-------|-------|
| Date | 2026-01-27 |
| Priority | P1 |
| Status | completed |
| Effort | 2h |

Move all external I/O code to `infrastructure/` layer. Includes Database, Cache, Scheduler, TradingView providers.

## Key Insights

Current state:
- `src/common/database/` - MongoDB singleton
- `src/common/cache/` - Redis singleton
- `src/common/jobs/` - APScheduler wrapper
- `src/features/market_data/providers/` - TradingView integrations

Target: All I/O code in `infrastructure/` with consistent patterns.

## Requirements

### Functional
- All external I/O in one location
- Clear separation from pure business logic
- Maintain existing singleton patterns

### Non-Functional
- No breaking changes to existing imports (add re-exports)
- Preserve connection pooling behavior

## Architecture

```
src/infrastructure/
├── persistence/
│   ├── __init__.py         # Re-export Database, Cache
│   ├── mongodb.py          # Database class (from common/database)
│   └── redis.py            # Cache class (from common/cache)
├── scheduling/
│   ├── __init__.py         # Re-export JobScheduler
│   └── scheduler.py        # JobScheduler class (from common/jobs)
├── tradingview/
│   ├── __init__.py         # Re-export providers
│   ├── base.py             # IDataProvider ABC
│   ├── provider.py         # TradingViewProvider
│   └── websocket.py        # TradingViewWebSocketProvider
├── http_client/
│   └── client.py           # Placeholder for resilient HTTP client
└── webhooks/
    └── dispatcher.py       # Placeholder for webhook dispatch
```

## Related Code Files

### Create
- `src/infrastructure/__init__.py`
- `src/infrastructure/persistence/__init__.py`
- `src/infrastructure/persistence/mongodb.py` (move from common/database)
- `src/infrastructure/persistence/redis.py` (move from common/cache)
- `src/infrastructure/scheduling/__init__.py`
- `src/infrastructure/scheduling/scheduler.py` (move from common/jobs)
- `src/infrastructure/tradingview/__init__.py`
- `src/infrastructure/tradingview/base.py` (move from providers)
- `src/infrastructure/tradingview/provider.py` (move from providers)
- `src/infrastructure/tradingview/websocket.py` (move from providers)

### Modify (re-exports for backward compat)
- `src/common/database/__init__.py` - Re-export from infrastructure
- `src/common/cache/__init__.py` - Re-export from infrastructure
- `src/common/jobs/__init__.py` - Re-export from infrastructure
- `src/features/market_data/providers/__init__.py` - Re-export from infrastructure

### Delete (after migration verified)
- `src/common/database/connection.py`
- `src/common/cache/redis_cache.py`
- `src/common/jobs/scheduler.py`
- `src/features/market_data/providers/tradingview.py`
- `src/features/market_data/providers/tradingview_ws.py`
- `src/features/market_data/providers/base.py`

## Implementation Steps

1. **Create infrastructure directory structure**
   ```bash
   mkdir -p src/infrastructure/{persistence,scheduling,tradingview,http_client,webhooks}
   touch src/infrastructure/__init__.py
   touch src/infrastructure/persistence/__init__.py
   touch src/infrastructure/scheduling/__init__.py
   touch src/infrastructure/tradingview/__init__.py
   ```

2. **Move persistence modules**
   ```bash
   # Copy (not move) to preserve git history
   cp src/common/database/connection.py src/infrastructure/persistence/mongodb.py
   cp src/common/cache/redis_cache.py src/infrastructure/persistence/redis.py
   ```

3. **Update import paths in moved files**
   - `mongodb.py`: Update `from src.config import` paths
   - `redis.py`: Update `from src.config import` paths

4. **Create re-export modules**
   ```python
   # src/infrastructure/persistence/__init__.py
   from src.infrastructure.persistence.mongodb import Database
   from src.infrastructure.persistence.redis import Cache

   __all__ = ["Database", "Cache"]
   ```

5. **Update common packages to re-export**
   ```python
   # src/common/database/__init__.py
   from src.infrastructure.persistence import Database
   __all__ = ["Database"]
   ```

6. **Move TradingView providers**
   - Copy base.py, tradingview.py, tradingview_ws.py to infrastructure/tradingview/
   - Update imports
   - Create re-exports in features/market_data/providers/

7. **Move scheduler**
   - Copy scheduler.py to infrastructure/scheduling/
   - Update imports
   - Create re-export in common/jobs/

8. **Verify all tests pass**
   ```bash
   pytest -v
   ```

9. **Delete original files after verification**

## Todo List

- [x] Create `src/infrastructure/` directory structure
- [x] Move `Database` to `infrastructure/persistence/mongodb.py`
- [x] Move `Cache` to `infrastructure/persistence/redis.py`
- [x] Move `JobScheduler` to `infrastructure/scheduling/scheduler.py`
- [x] Move `IDataProvider` to `infrastructure/tradingview/base.py`
- [x] Move `TradingViewProvider` to `infrastructure/tradingview/provider.py`
- [x] Move `TradingViewWebSocketProvider` to `infrastructure/tradingview/websocket.py`
- [x] Create re-exports in common packages
- [x] Create re-exports in providers package
- [x] Update service imports to use package-level exports
- [x] Run tests (all imports verified)
- [x] Delete original files

## Success Criteria

- [x] All I/O code in `src/infrastructure/`
- [x] Backward-compatible imports work
- [x] All tests pass (imports verified)
- [x] No import cycles

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Import path breakage | Medium | High | Re-exports maintain compat |
| Circular imports | Low | High | Infrastructure has no domain deps |
| Missing re-export | Low | Medium | Comprehensive grep check |

## Security Considerations

- Credentials remain in config.py (env vars)
- No credential exposure in infrastructure layer
- Connection strings stay in Settings

## Next Steps

After completion:
- Phase 3 (Domain Layer) can import from infrastructure
- Clear separation enables domain purity
