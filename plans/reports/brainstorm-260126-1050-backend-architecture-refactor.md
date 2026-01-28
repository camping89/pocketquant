# Brainstorm Report: Backend Architecture Refactor

**Date:** 2026-01-26
**Status:** Agreed
**Scope:** Migrate to No-Repository CQRS + Add Infrastructure Interfaces + Rename Managers

---

## Problem Statement

Current codebase uses **Repository Pattern** (OHLCVRepository, SymbolRepository) but the target architecture (Backend Architecture Review skill) recommends:

1. **No Repository** - Direct DB access in Services/Handlers
2. **Infrastructure Layer** - Provider interfaces for external services
3. **Manager/Service Naming** - Manager = pure logic, Service = orchestration with I/O
4. **Data Ownership Tracking** - Which slice owns which collection (deferred)

---

## Current State Analysis

### Architecture Assessment

| Aspect | Current | Target | Gap |
|--------|---------|--------|-----|
| Repository Layer | ✅ Exists (2 repos) | ❌ Remove | **Major refactor** |
| Provider Interfaces | ❌ Concrete only | ✅ Add IDataProvider | **New layer** |
| Manager Naming | ❌ No managers | ✅ BarManager | **Rename + move** |
| Data Ownership | ❌ None | ⏸️ Deferred | Skip for now |
| Error Handling | ⚠️ Some bare except | ✅ Specific only | **Minor fixes** |

### Files to Modify

| File | Changes |
|------|---------|
| `src/features/market_data/repositories/ohlcv_repository.py` | **DELETE** - Move logic to services |
| `src/features/market_data/repositories/symbol_repository.py` | **DELETE** - Move logic to services |
| `src/features/market_data/services/data_sync_service.py` | Add direct DB access |
| `src/features/market_data/services/quote_aggregator.py` | **RENAME** to `managers/bar_manager.py` |
| `src/features/market_data/services/quote_service.py` | Update import |
| `src/features/market_data/api/routes.py` | Update imports, direct DB for simple queries |
| `src/features/market_data/jobs/sync_jobs.py` | Update imports |
| `src/infrastructure/` | **NEW** - Add interfaces folder |
| `src/infrastructure/interfaces/data_provider.py` | **NEW** - IDataProvider ABC |
| `src/features/market_data/providers/tradingview.py` | Implement IDataProvider |
| `src/common/jobs/scheduler.py:163` | Fix bare `except` |

---

## Agreed Approach

### 1. Remove Repository Layer → Direct DB in Services

**Before:**
```python
# data_sync_service.py
from repositories.ohlcv_repository import OHLCVRepository

upserted_count = await OHLCVRepository.upsert_many(records)
```

**After:**
```python
# data_sync_service.py
from src.common.database import Database

collection = Database.get_collection("ohlcv")
# Direct bulk_write operation inline
```

**Migration Strategy:**
1. Move repository methods inline to calling services
2. For shared query logic, keep as private methods in service
3. Simple queries (list all, get by ID) can be direct in handlers

### 2. Add Infrastructure Layer with Interfaces

**New Structure:**
```
src/
├── infrastructure/
│   ├── __init__.py
│   └── interfaces/
│       ├── __init__.py
│       └── data_provider.py   # IDataProvider ABC
```

**Interface Definition:**
```python
# infrastructure/interfaces/data_provider.py
from abc import ABC, abstractmethod
from src.features.market_data.models.ohlcv import OHLCVCreate, Interval

class IDataProvider(ABC):
    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[OHLCVCreate]: ...

    @abstractmethod
    def close(self) -> None: ...
```

**Provider Implementation:**
```python
# providers/tradingview.py
from src.infrastructure.interfaces import IDataProvider

class TradingViewProvider(IDataProvider):
    async def fetch_ohlcv(...) -> list[OHLCVCreate]:
        # existing implementation
```

### 3. Rename QuoteAggregator → BarManager

**Rationale:** QuoteAggregator contains pure domain logic (bar building, tick aggregation) with no external I/O. Per skill guidelines, this is a **Manager** not a Service.

**Changes:**
- Rename file: `services/quote_aggregator.py` → `managers/bar_manager.py`
- Rename class: `QuoteAggregator` → `BarManager`
- Rename inner class: `BarBuilder` stays (already correct)
- Update all imports

**Note:** `BarManager` will still call `OHLCVRepository` for saves. After repository removal, it will use `Database.get_collection()` directly.

### 4. Fix Error Handling

**Current Issues:**
- `scheduler.py:163` - bare `except Exception:` without logging
- `tradingview_ws.py:204` - bare `except Exception:`

**Fix:** Add specific exception types or at minimum log the error:
```python
# Before
except Exception:
    return False

# After
except JobLookupError:
    logger.warning("scheduler.job_not_found", job_id=job_id)
    return False
```

---

## Implementation Considerations

### Breaking Changes
- All imports from `repositories/` will break
- Tests mocking repositories need update
- Background jobs reference repositories directly

### Migration Order (Recommended)
1. **Phase 1:** Add infrastructure interfaces (non-breaking)
2. **Phase 2:** Rename QuoteAggregator → BarManager (low risk)
3. **Phase 3:** Migrate OHLCVRepository → DataSyncService (medium risk)
4. **Phase 4:** Migrate SymbolRepository → routes/services (medium risk)
5. **Phase 5:** Delete repository files, update all imports
6. **Phase 6:** Fix error handling issues

### Risks

| Risk | Mitigation |
|------|------------|
| Breaking existing tests | Run full test suite after each phase |
| Duplicate code after inlining | Extract common DB operations as private methods |
| Increased service complexity | Keep services focused, split if >200 LOC |

---

## Success Criteria

- [ ] No `repositories/` folder exists
- [ ] All DB access through `Database.get_collection()` in services/handlers
- [ ] `infrastructure/interfaces/data_provider.py` exists with IDataProvider
- [ ] TradingViewProvider implements IDataProvider
- [ ] `managers/bar_manager.py` exists (renamed from quote_aggregator)
- [ ] No bare `except:` or `except Exception:` without logging
- [ ] All tests pass
- [ ] Code compiles without errors

---

## Estimated Effort

| Phase | Effort | Files Changed |
|-------|--------|---------------|
| Infrastructure interfaces | 30 min | 3 new files |
| Rename BarManager | 20 min | 4 files |
| Migrate OHLCVRepository | 1.5 hr | 5 files |
| Migrate SymbolRepository | 30 min | 3 files |
| Error handling fixes | 20 min | 2 files |
| Testing & verification | 1 hr | - |
| **Total** | **~4 hours** | **~15 files** |

---

## Next Steps

1. Create detailed implementation plan with phases
2. Execute Phase 1 (infrastructure interfaces) first
3. Run tests after each phase
4. Update documentation after completion

---

## Unresolved Questions

None - all decisions made.
