# Motor Deprecation & PyMongo Async Migration Research

**Date:** 2026-01-21 | **Status:** Complete

## 1. Motor Deprecation Timeline

**CRITICAL DATES:**
- **May 14, 2025**: Motor officially deprecated (already occurred)
- **May 14, 2026**: Bug fix support ends (~16 months remaining)
- **May 14, 2027**: Critical fix support ends (~28 months remaining)

Motor deprecation favors PyMongo's native Async API, which unifies PyMongo and Motor into single codebase.

**References:**
- [Motor Documentation](https://motor.readthedocs.io/en/latest/)
- [Motor Deprecation Announcement](https://www.mongodb.com/community/forums/t/motor-3-7-1-released/321388)

## 2. Deprecation Rationale

Motor historically used thread pools for async operations. PyMongo Async implements asyncio support **directly**, eliminating overhead:
- **Performance**: PyMongo Async shows improved performance over Motor in most cases
- **Maintenance**: Single driver reduces MongoDB's maintenance burden
- **Architecture**: Direct asyncio integration vs. thread pool wrapper

## 3. Migration Path (Motor → PyMongo Async)

**Quick migration (most cases):**
```python
# Motor
from motor.motor_asyncio import AsyncIOMotorClient
client = AsyncIOMotorClient(...)

# PyMongo Async
from pymongo.asynchronous import AsyncClient
client = AsyncClient(...)
```

**Key Replacements:**
- `MotorClient` → `AsyncMongoClient` (or `AsyncClient`)
- All async methods remain `async`/`await` compatible
- Import statements updated to `pymongo.asynchronous`

**Breaking Changes:**
- `AsyncMongoClient.__init__()` no longer accepts `io_loop` parameter
- `AsyncCursor.each()` removed (use `async for` instead)
- `find()` returns `AsyncCursor` (not directly iterable)

**Cursor Iteration Pattern:**
```python
# Motor/Old
async for doc in collection.find():
    pass

# PyMongo Async - same pattern works
async for doc in collection.find():
    pass

# Or convert to list
docs = await collection.find().to_list(None)
```

**References:**
- [Official Migration Guide](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/motor-async-migration/)
- [PyMongo Async Migration](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/)

## 4. Connection Pooling & Performance

**Default Pool Settings:**
- `maxPoolSize`: 100
- `minPoolSize`: 0
- `maxConnecting`: 2 (rate limiting per server)
- `maxIdleTimeMS`: None (unlimited)
- `waitQueueTimeoutMS`: None (unlimited wait)

**Key Optimization Patterns:**
- `maxConnecting=2` prevents connection storms
- Increase `minPoolSize` for high-concurrency apps (default 0 inefficient for FastAPI)
- Tune `maxIdleTimeMS` for long-running services
- Keep `maxPoolSize` ≤ 100 unless proven needed

**PyMongo Async uses async sockets**, not thread pools → lower latency, better resource utilization.

**References:**
- [Connection Pool Configuration](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/connection-options/connection-pools/)
- [Performance Tuning](https://www.mongodb.com/docs/manual/tutorial/connection-pool-performance-tuning/)

## 5. FastAPI Integration Best Practices

**Lifespan Management:**
- Initialize `AsyncClient` in lifespan context manager (FastAPI 0.93+)
- Reuse single client instance across app lifetime
- Call `client.close()` on shutdown

**Sensitive Data:**
- Always store connection strings in environment variables (`.env`)
- Never commit credentials to version control

**Type Annotations:**
- Import from `pymongo.asynchronous.collection import AsyncCollection`
- Type hints: `AsyncCollection[dict]` for generic operations

**References:**
- [FastAPI Integration Guide](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/integrations/fastapi-integration/)
- [8 Best Practices](https://www.mongodb.com/developer/products/mongodb/8-fastapi-mongodb-best-practices/)

## 6. Common Migration Pitfalls

1. **Forgetting `await` on async methods** - Will cause "coroutine was never awaited" errors
2. **Using `.each()` pattern** - Method removed; migrate to `async for` or `.to_list()`
3. **Passing `io_loop`** - Parameter ignored in PyMongo Async; remove it
4. **Ignoring pool sizing** - Default minPoolSize=0 inefficient for FastAPI; set to 10-20 for concurrent apps
5. **Not closing client** - Memory leak if client not closed on app shutdown

## 7. Code Quality Considerations

**Type Safety:**
- Use `AsyncMongoClient` type hints
- Import `AsyncCollection[dict]` for type checking
- Leverage `pymongo.asynchronous` module structure

**Error Handling:**
- Same exception types as PyMongo (e.g., `pymongo.errors.OperationFailure`)
- Network timeouts: configure via `connectTimeoutMS`, `socketTimeoutMS`

## 8. Migration Timeline Recommendation

**Phase 1** (Q1 2026): Plan & test migration on new branches
**Phase 2** (Q2 2026): Gradual rollout; keep Motor as fallback if critical issues surface
**Phase 3** (By May 2026): Complete migration before bug fix support ends

Waiting past May 2026 limits future support; only critical fixes available until May 2027.

---

## Unresolved Questions

- What's optimal `minPoolSize` for pocketquant's concurrent workload? (Requires load testing)
- Should we maintain Motor compatibility layer during transition? (YAGNI principle says no)
