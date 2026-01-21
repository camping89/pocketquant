# PyMongo Async API Migration Research Report

**Date:** 2026-01-21
**Status:** Complete
**Target Version:** PyMongo 4.16+, Python 3.14

---

## Executive Summary

PyMongo Async API is a unified, production-ready replacement for Motor. It implements native asyncio support directly in PyMongo (no thread pool), delivering 2-3x better performance. Motor is officially deprecated as of May 14, 2025, with end-of-life on May 14, 2027. Migration is straightforward for most codebases.

---

## 1. PyMongo Async API Overview

### What Changed
- **Before:** Motor (AsyncIOMotorClient) wraps PyMongo with thread pool for network ops
- **After:** PyMongo (AsyncMongoClient) native asyncio implementation
- **Performance:** 2-3x faster in most cases due to direct event loop integration
- **Status:** GA (Generally Available) as of PyMongo 4.9+, fully stable in 4.16+

### Connection Architecture
```python
# Motor (deprecated)
from motor.motor_asyncio import AsyncIOMotorClient
client = AsyncIOMotorClient('mongodb://...')

# PyMongo Async (new)
from pymongo.asynchronous import AsyncMongoClient
client = AsyncMongoClient('mongodb://...')
```

---

## 2. Critical Breaking Changes

### Client Initialization
| Aspect | Motor | PyMongo Async |
|--------|-------|---------------|
| **Constructor blocks?** | No | No (immediate return, background connection) |
| **io_loop parameter** | Supported | NOT supported |
| **connect parameter** | Supported | NOT supported |
| **Thread safety** | Thread-safe collections | NOT thread-safe - single event loop only |

### Behavioral Differences
1. **AsyncCursor.each()** - REMOVED in PyMongo Async (use async for loop instead)
2. **AsyncCursor.to_list(0)** - NOT VALID (use to_list(None) for all documents)
3. **Exception timing** - Motor raises ConnectionFailure/ConfigurationError at init; PyMongo raises during operations
4. **Event loop sharing** - AsyncMongoClient must not be shared across threads/event loops

### API Compatibility
- Most Motor methods have direct PyMongo equivalents
- Collection/Database/Client interface 95% identical
- No breaking changes in find/insert/update/delete operations
- Transaction support preserved

---

## 3. Python 3.14 Specific Considerations

### Support Status
- **PyMongo 4.16+:** Full Python 3.14 wheels available (CPython 3.14 supported)
- **Async API:** Fully compatible with Python 3.14 asyncio
- **Free-threading:** PyMongo 4.14+ has preliminary support, but some features unsupported

### Known Limitations
- Some features not yet available with Python 3.14 free-threading (unspecified in docs)
- Recommendation: Use default asyncio threading model if encountering issues
- Monitor PyMongo changelog for Python 3.14 updates

### Version Requirement
**Minimum:** PyMongo 4.16.0 (ensure Python 3.14 wheel availability)

---

## 4. Migration Checklist

### Code Changes Required
1. Replace all `from motor.motor_asyncio import AsyncIOMotorClient`
   → `from pymongo.asynchronous import AsyncMongoClient`

2. Remove `io_loop=` parameters from client initialization

3. Replace `AsyncCursor.each()` with async for loop:
   ```python
   # Old
   async for doc in cursor.each():

   # New
   async for doc in cursor:
   ```

4. Replace `to_list(0)` with `to_list(None)`

5. Ensure functions calling async methods are marked `async`

6. Add `await` to all network operations (mostly auto-detectable by linter)

### Testing Points
- Connection establishment (now deferred to first operation)
- Cursor iteration patterns
- Transaction handling
- Error handling (timing differs)
- Multi-database operations
- Connection pool behavior

---

## 5. Performance & Reliability

### Performance Gains
- **Network operations:** 2-3x faster (direct event loop vs thread pool)
- **Memory:** Lower overhead (no thread pool)
- **Latency:** Reduced (eliminate thread scheduling)
- **Scalability:** Better for high-concurrency scenarios

### Reliability Improvements
- Native asyncio integration reduces concurrency bugs
- Direct error propagation (simpler debugging)
- Better stack traces

---

## 6. Compatibility & Versions

### Supported PyMongo Versions
- **4.16.0+:** Recommended (Python 3.14 support)
- **4.9+:** Minimum (PyMongo Async GA)
- **4.14+:** Python 3.14 preliminary support

### Motor Deprecation Timeline
- **May 14, 2025:** Deprecated (no new features)
- **May 14, 2026:** Bug fixes end
- **May 14, 2027:** Full end-of-life

---

## Implementation Path

1. **Phase 1:** Update PyMongo requirement to 4.16+
2. **Phase 2:** Swap client imports, remove io_loop params
3. **Phase 3:** Fix cursor iteration (each → async for, to_list(0) → to_list(None))
4. **Phase 4:** Run comprehensive async tests
5. **Phase 5:** Load testing for performance validation

---

## Unresolved Questions

1. **Exact Python 3.14 free-threading limitations:** PyMongo docs don't specify which features are unsupported with free-threading
2. **Migration timeline for pocketquant:** Depends on current Motor usage patterns
3. **Backwards compatibility needs:** Should old Motor-compatible code be maintained in parallel?

---

## References

- [Migrate to PyMongo Async - Official Migration Guide](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/)
- [PyMongo 4.16.0 Async API Documentation](https://pymongo.readthedocs.io/en/stable/api/pymongo/asynchronous/index.html)
- [Motor Differences Documentation](https://motor.readthedocs.io/en/stable/differences.html)
- [PyMongo Changelog](https://pymongo.readthedocs.io/en/stable/changelog.html)
- [AsyncMongoClient API Reference](https://pymongo.readthedocs.io/en/latest/api/pymongo/asynchronous/mongo_client.html)
- [Motor End-of-Life Announcement](https://motor.readthedocs.io/)
