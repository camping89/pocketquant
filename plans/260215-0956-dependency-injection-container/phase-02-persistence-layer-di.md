# Phase 2: Convert Persistence Layer to Instance-Based DI

## Context Links

- [Plan overview](./plan.md)
- [Phase 1](./phase-01-container-skeleton.md)
- [Database singleton](../../src/persistence/mongodb.py)
- [Cache singleton](../../src/persistence/redis.py)
- [BaseRepository](../../src/persistence/base_repository.py)
- [Order repo example](../../src/persistence/repositories/order_repository.py)

## Overview

- **Priority:** P1 (largest phase, most files touched)
- **Status:** pending
- **Effort:** 3h
- **Description:** Convert Database, Cache, and all 7 repositories from static class-method singletons to instance-based classes managed by DI container. Database and Cache become `Resource` providers (async init/shutdown). Repositories become `Singleton` providers injected with Database instance.

## Key Insights

- Current `Database` class uses class-level `_client` and `_database` -- must move to instance vars
- Current `BaseRepository._collection()` calls `Database.get_collection()` globally -- must accept Database instance
- All 7 repositories use `@staticmethod` or `@classmethod` with `cls._collection()` -- must convert to instance methods
- `Cache` has 9 class methods (get, set, delete, etc.) -- all must become instance methods
- Re-export modules (`src/common/database/`, `src/common/cache/`) need updating
- `dependency-injector` `Resource` provider supports async init/shutdown via generator pattern
- Motor (pymongo async) manages its own connection pool, so Database is truly a singleton resource

## Requirements

### Functional
- Database connects/disconnects via container Resource lifecycle
- Cache connects/disconnects via container Resource lifecycle
- All repositories receive Database instance via constructor
- All existing repository method signatures unchanged (just `self` instead of `cls`)
- All callers updated to use instance methods

### Non-Functional
- No behavioral change to any API endpoint
- Connection pooling behavior unchanged
- Each file stays under 200 LOC

## Architecture

### Database: Class-Method -> Instance-Based Resource

```python
# src/persistence/mongodb.py (AFTER)
class Database:
    def __init__(self) -> None:
        self._client: AsyncMongoClient | None = None
        self._database: AsyncDatabase | None = None

    async def connect(self, settings: Settings) -> None:
        client = AsyncMongoClient(
            str(settings.mongodb_url),
            minPoolSize=settings.mongodb_min_pool_size,
            maxPoolSize=settings.mongodb_max_pool_size,
            serverSelectionTimeoutMS=5000,
        )
        await client.server_info()
        self._client = client
        self._database = client[settings.mongodb_database]

    async def disconnect(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
            self._database = None

    def get_database(self) -> AsyncDatabase:
        if self._database is None:
            raise RuntimeError("Database not connected.")
        return self._database

    def get_collection(self, name: str):
        return self.get_database()[name]
```

### Database Resource Provider

```python
# In src/container.py
import asyncio
from collections.abc import AsyncIterator
from dependency_injector import providers

async def init_database(settings: Settings) -> AsyncIterator[Database]:
    """Resource provider: connect on init, disconnect on shutdown."""
    db = Database()
    await db.connect(settings)
    yield db
    await db.disconnect()

class AppContainer(containers.DeclarativeContainer):
    settings = providers.Singleton(get_settings)
    database = providers.Resource(init_database, settings=settings)
```

### Cache: Same Pattern

```python
async def init_cache(settings: Settings) -> AsyncIterator[Cache]:
    cache = Cache()
    await cache.connect(settings)
    yield cache
    await cache.disconnect()

class AppContainer(containers.DeclarativeContainer):
    ...
    cache = providers.Resource(init_cache, settings=settings)
```

### BaseRepository: Accept Database Instance

```python
# src/persistence/base_repository.py (AFTER)
class BaseRepository:
    _collection_name: str

    def __init__(self, database: Database) -> None:
        self._database = database

    def _collection(self):
        return self._database.get_collection(self._collection_name)
```

### Repository Example (OrderRepository)

```python
# BEFORE: @staticmethod with cls._collection()
class OrderRepository(BaseRepository):
    _collection_name = COLLECTION_ORDERS

    @staticmethod
    async def save(order: OrderAggregate) -> None:
        collection = OrderRepository._collection()
        ...

# AFTER: instance method with self._collection()
class OrderRepository(BaseRepository):
    _collection_name = COLLECTION_ORDERS

    async def save(self, order: OrderAggregate) -> None:
        collection = self._collection()
        ...
```

### Container Providers for Repositories

```python
# In src/container.py
class AppContainer(containers.DeclarativeContainer):
    ...
    order_repository = providers.Singleton(OrderRepository, database=database)
    position_repository = providers.Singleton(PositionRepository, database=database)
    backtest_repository = providers.Singleton(BacktestRepository, database=database)
    ohlcv_repository = providers.Singleton(OHLCVRepository, database=database)
    symbol_repository = providers.Singleton(SymbolRepository, database=database)
    sync_status_repository = providers.Singleton(SyncStatusRepository, database=database)
    optimization_repository = providers.Singleton(OptimizationRepository, database=database)
```

## Related Code Files

| File | Action | Notes |
|------|--------|-------|
| `src/persistence/mongodb.py` | modify | Remove class vars, add `__init__`, instance methods |
| `src/persistence/redis.py` | modify | Remove class vars, add `__init__`, instance methods |
| `src/persistence/base_repository.py` | modify | Add `__init__(self, database)`, instance `_collection()` |
| `src/persistence/repositories/order_repository.py` | modify | `@staticmethod` -> instance methods |
| `src/persistence/repositories/position_repository.py` | modify | Same pattern |
| `src/persistence/repositories/backtest_repository.py` | modify | Same pattern |
| `src/persistence/repositories/ohlcv_repository.py` | modify | Same pattern |
| `src/persistence/repositories/symbol_repository.py` | modify | Same pattern |
| `src/persistence/repositories/sync_status_repository.py` | modify | Same pattern |
| `src/persistence/repositories/optimization_repository.py` | modify | Same pattern |
| `src/persistence/__init__.py` | modify | Update exports |
| `src/common/database/__init__.py` | modify | Update re-exports |
| `src/common/cache/__init__.py` | modify | Update re-exports |
| `src/container.py` | modify | Add Database, Cache, all repository providers |
| `src/common/health/checks.py` | modify | Health checks need Database/Cache instances |

### Callers That Use Repositories Directly (must update in Phase 4/5)

Handlers that call `OHLCVRepository.get_bars()` etc. as static calls will break. Two strategies:

**Strategy A (recommended for this phase):** Keep backward-compatible static fallback during transition.
- Add a module-level default instance set during container init
- Existing static callers continue to work
- Gradually migrate in Phase 4 when handlers get DI

**Strategy B:** Update all callers immediately.
- More churn in this phase but cleaner
- Risk: touching handler files conflicts with Phase 4 scope

**Decision: Strategy A** -- add `_default_instance` pattern to BaseRepository for backward compat. Remove in Phase 5 cleanup.

```python
class BaseRepository:
    _collection_name: str
    _default_instance: ClassVar[Self | None] = None

    def __init__(self, database: Database) -> None:
        self._database = database
        # Set as default for backward compat (removed in Phase 5)
        type(self)._default_instance = self

    def _collection(self):
        return self._database.get_collection(self._collection_name)

    @classmethod
    def _get_collection(cls):
        """Backward-compatible class method. Deprecated, use instance."""
        if cls._default_instance is None:
            # Fallback to old static pattern during migration
            from src.persistence.mongodb import Database as StaticDB
            return StaticDB.get_collection(cls._collection_name)
        return cls._default_instance._collection()
```

## Implementation Steps

1. **Convert `src/persistence/mongodb.py`**:
   - Move `_client` and `_database` from class vars to `__init__`
   - Convert `connect()`, `disconnect()`, `get_database()`, `get_collection()` from `@classmethod` to instance methods
   - Remove `@classmethod` decorators, change `cls` to `self`
   - Keep `get_database()` context manager as standalone function
   - Update logging

2. **Convert `src/persistence/redis.py`**:
   - Move `_client`, `_default_ttl` from class vars to `__init__`
   - Convert all 9 methods from `@classmethod` to instance methods
   - Keep `get_cache()` context manager

3. **Convert `src/persistence/base_repository.py`**:
   - Add `__init__(self, database: Database)`
   - Convert `_collection()` to instance method
   - Add `_default_instance` backward compat pattern

4. **Convert all 7 repository files**:
   - For each: remove `@staticmethod`/`@classmethod`, add `self` parameter
   - Change `cls._collection()` / `ClassName._collection()` to `self._collection()`
   - Keep method signatures otherwise identical
   - Files: order, position, backtest, ohlcv, symbol, sync_status, optimization

5. **Update `src/container.py`**:
   - Add `init_database` async generator resource provider
   - Add `init_cache` async generator resource provider
   - Add all 7 repository Singleton providers

6. **Update re-export modules**:
   - `src/common/database/__init__.py` -- adjust if needed
   - `src/common/cache/__init__.py` -- adjust if needed
   - `src/persistence/__init__.py` -- update exports

7. **Update `src/common/health/checks.py`**:
   - Health check functions currently call `Database.get_database()` / `Cache.get_client()` statically
   - For now, keep backward compat via default instance pattern
   - Full DI injection happens in Phase 5

8. **Update callers that directly import Cache**:
   - `src/application/market_data/bar_manager.py` -- uses `Cache.set()`
   - `src/application/market_data/quote_service.py` -- uses `Cache.set()`
   - `src/features/market_data/ohlcv/get_ohlcv/handler.py` -- uses `Cache.get()/set()`
   - `src/features/market_data/quotes/get_latest/handler.py` -- uses `Cache.get()`
   - `src/features/market_data/sync/sync_one/handler.py` -- uses `Cache.delete_pattern()`
   - These will use backward-compat static access until Phase 4 converts them

<!-- Red Team: Test fixture collapse — 2026-02-15 -->
9. **Migrate test fixtures FIRST (before running tests)**:
   - Create `tests/conftest.py` container fixture using `container.override()`:
     ```python
     @pytest.fixture
     def container():
         c = AppContainer()
         c.database.override(providers.Object(mock_database))
         c.cache.override(providers.Object(mock_cache))
         yield c
         c.reset_override()
     ```
   - Create `mock_database` and `mock_cache` fixtures returning AsyncMock instances
   - Update all repository test fixtures to accept Database instance via constructor
   - Pattern: `repo = OrderRepository(database=mock_database)` instead of patching classmethods

<!-- Red Team: Backward compat zombie path — 2026-02-15 -->
10. **Add deprecation warning to `_default_instance` fallback**:
    - Log warning on every static access: `logger.warning("deprecated_static_access", repo=cls.__name__)`
    - Grep validation: `grep -r "Repository\.[a-z_]\+(" src/features/` must return zero after Phase 4

11. **Run tests and lint**

## Todo List

- [ ] Convert `Database` from class-method to instance-based
- [ ] Convert `Cache` from class-method to instance-based
- [ ] Convert `BaseRepository` to accept Database in constructor
- [ ] Convert `OrderRepository` to instance methods
- [ ] Convert `PositionRepository` to instance methods
- [ ] Convert `BacktestRepository` to instance methods
- [ ] Convert `OHLCVRepository` to instance methods
- [ ] Convert `SymbolRepository` to instance methods
- [ ] Convert `SyncStatusRepository` to instance methods
- [ ] Convert `OptimizationRepository` to instance methods
- [ ] Add Database/Cache Resource providers to container
- [ ] Add all 7 repository Singleton providers to container
- [ ] Update `src/persistence/__init__.py` exports
- [ ] Update `src/common/database/__init__.py` re-exports
- [ ] Update `src/common/cache/__init__.py` re-exports
- [ ] Verify backward-compat static access works for unmigrated callers
- [ ] Run `ruff check src/persistence/`
- [ ] Run `pyright src/persistence/`
- [ ] Run full test suite

## Success Criteria

- Database/Cache init and shutdown managed by container Resource lifecycle
- All repositories instantiated via container with Database injected
- Backward-compat static access still works for handlers not yet migrated
- `ensure_all_indexes()` works via repository instances from container
- All existing tests pass (possibly with fixture updates)
- No connection leaks on shutdown

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking all repository callers at once | High | `_default_instance` backward compat pattern |
| Test fixtures mock class methods | Medium | Update fixtures to mock instances; keep old mocks working via compat |
| Connection not closed on crash | Medium | Resource provider's generator ensures cleanup |
| Repository `ensure_indexes` called before container init | Medium | Call after `container.init_resources()` |

## Security Considerations

- No credential changes; settings injection unchanged
- MongoDB/Redis connection strings still from env vars

## Next Steps

- Phase 3: Register infrastructure services (JobScheduler, TradingViewProvider, etc.)
