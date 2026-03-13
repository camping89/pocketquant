# Test Report: Drop DI Pattern Refactoring

**Date:** 2026-03-13
**Status:** PASS (with findings)
**Tested Branch:** feat/strategy-init

---

## Executive Summary

All **60 tests pass** successfully. Refactoring from `dependency-injector` to plain Python constructors + FastAPI Depends is **test-safe**. However, **1 legacy test script still references old container pattern** — requires immediate remediation before deployment.

---

## Test Results Overview

| Metric | Value |
|--------|-------|
| **Total Tests Run** | 60 |
| **Passed** | 60 (100%) |
| **Failed** | 0 |
| **Skipped** | 0 |
| **Test Execution Time** | 11.69s |
| **Test Framework** | pytest 9.0.2 |
| **Python Version** | 3.14.2 |

### Test Distribution

- **Unit Tests:** 57 (95%)
  - Common (event_bus, mediator): 8 tests
  - Domain (value objects): 11 tests
  - Infrastructure (TradingView websocket): 38 tests
- **Integration Tests:** 3 (5%)
  - TradingView websocket integration: 3 tests

---

## Code Coverage Analysis

**Overall Coverage:** 21% (4537 / 5769 lines)

### Coverage by Module

| Module | Coverage | Status |
|--------|----------|--------|
| `src/infrastructure/tradingview/` | 82% | Good |
| `src/persistence/schemas/ohlcv/` | 72% | Good |
| `src/infrastructure/brokers/models/` | 87% | Good |
| `src/infrastructure/webhooks/` | 90% | Good |
| **Critical Uncovered Areas** | | |
| `src/main.py` | 0% | NOT TESTED |
| `src/main_extensions.py` | 0% | NOT TESTED |
| `src/handler_registration.py` | 0% | NOT TESTED |
| `src/services.py` | 0% | NOT TESTED |
| `src/features/` (routes/handlers) | 0% | NOT TESTED |
| `src/persistence/` (repositories) | 0-35% | MOSTLY UNCOVERED |

**Issue:** New infrastructure files (services, handler_registration, dependencies) have **zero integration test coverage**. This is expected for new code but indicates reliance on manual testing or higher-level integration tests.

---

## Old Pattern References Found

### Critical Finding: Legacy Test Script

**File:** `testscripts/run_sync_jobs.py`

**Issue:** Still imports deleted `src.container` module:

```python
from src.container import AppContainer, register_all_handlers  # DOES NOT EXIST

container = AppContainer()
await container.init_resources()
register_all_handlers(container)
```

**Status:** Script is **non-functional** — will fail on execution.

### Expected References (OK)

**File:** `src/services.py`
**Line:** 1 (comment only)
**Content:** `"""Application service registry — replaces dependency-injector container.`

This is documentation. Not a functional reference.

---

## Test Warnings

### 2 PytestCollectionWarnings (Non-Critical)

```
tests/unit/common/test_event_bus.py:11
  PytestCollectionWarning: cannot collect test class 'TestEvent'
  because it has a __init__ constructor

tests/unit/common/test_mediator.py:15
  PytestCollectionWarning: cannot collect test class 'TestCommand'
  because it has a __init__ constructor
```

**Cause:** Test helper dataclasses have `@dataclass` + `__init__` which pytest interprets as test classes (name starts with `Test`).
**Impact:** None. Tests still pass. Classes are properly used as command/event models, not actual test classes.
**Recommendation:** Rename dataclasses (remove `Test` prefix) to silence warnings, or mark pytest.ini with test path patterns.

---

## Pattern Migration Verification

### Confirmed Deleted
- ✅ `src/container.py` — Verified deleted
- ✅ `src.container` import references in main codebase — All replaced

### Confirmed Created
- ✅ `src/services.py` — Services dataclass with 26 fields
- ✅ `src/handler_registration.py` — 27 handlers explicitly constructed
- ✅ `src/dependencies.py` — Route-level Depends() functions
- ✅ `src/main.py` — Lifespan with explicit init/shutdown

### Confirmed Updated
- ✅ `src/main_extensions.py` — Accepts Services instead of AppContainer
- ✅ All route imports — Changed from `src.common.mediator.dependencies` (old) to `src.dependencies` (new)

### Grep Results Summary

| Search Term | Files Found | Status |
|-------------|------------|--------|
| `AppContainer` | 1 (testscripts/run_sync_jobs.py) | ❌ BROKEN |
| `from src.container` | 1 (testscripts/run_sync_jobs.py) | ❌ BROKEN |
| `resolve(` | 0 | ✅ CLEAN |
| `app.state.container` | 0 | ✅ CLEAN |
| `dependency_injector` | 1 (src/services.py comment) | ✅ OK |

---

## Failed Tests

**None.** All 60 tests pass.

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Total Suite Execution | 11.69s |
| Avg Test Duration | 195ms |
| Longest Test | ~500ms (likely websocket integration) |
| Shortest Test | ~5ms |

**Analysis:** Test performance is acceptable. No bottlenecks detected.

---

## Critical Issues

### 1. Broken Test Script: `testscripts/run_sync_jobs.py`

**Severity:** HIGH
**Impact:** Script cannot be executed; will crash on import
**Root Cause:** Imports deleted `AppContainer` from non-existent `src.container`

**Required Fix:**
```python
# OLD (broken)
from src.container import AppContainer, register_all_handlers

# NEW (correct)
from src.dependencies import Services  # If Services needed elsewhere
from src.handler_registration import register_all_handlers
from src.services import Services

# Then update code to:
# 1. Create Services instance (not AppContainer)
# 2. Call register_all_handlers(services) instead of container
```

**Action:** Update testscripts/run_sync_jobs.py before it's executed in any manual testing or CI/CD workflow.

---

## Recommendations

### Priority 1 (Blocking)
1. **Fix `testscripts/run_sync_jobs.py`**
   - Remove `AppContainer` import
   - Replace with `Services` dataclass initialization
   - Update container method calls to services field access
   - Add unit test for this script or integrate into CI

### Priority 2 (Coverage)
2. **Add integration tests for main.py lifespan**
   - Test Services initialization
   - Test lifespan startup/shutdown
   - Verify all handlers are registered
   - Currently 0% coverage on critical infrastructure files

3. **Add route integration tests**
   - Test FastAPI Depends() injection
   - Verify Services flows through to handlers
   - Currently 0% coverage on all feature routes

### Priority 3 (Code Quality)
4. **Resolve pytest dataclass warnings**
   - Rename `TestEvent` → `EventCommand` (remove Test prefix)
   - Rename `TestCommand` → `SampleCommand`
   - Or configure pytest to only collect from `tests/` directory

5. **Add documentation**
   - Create `docs/dependency-injection-migration.md` explaining:
     - Why: (old pattern limitations)
     - New pattern: Services + Depends()
     - How to add new services/routes
     - Migration checklist for third-party integrations

### Priority 4 (Long-term)
6. **Improve repository coverage**
   - Add tests for MongoDB repository operations
   - Test persistence layer (currently 0-35% coverage)
   - Mock DB/Redis where external dependencies exist

---

## Success Criteria Met

| Criterion | Status | Notes |
|-----------|--------|-------|
| All existing tests pass | ✅ | 60/60 passing |
| No `AppContainer` in main code | ✅ | Found only in deprecated testscript |
| No `from src.container` imports | ✅ | Found only in deprecated testscript |
| No `resolve(` calls | ✅ | Fully eliminated |
| No `app.state.container` | ✅ | Not used in new pattern |
| Build is clean | ✅ | All tests pass, no syntax errors |

---

## Unresolved Questions

1. **Should `testscripts/run_sync_jobs.py` be promoted to a full integration test in `tests/integration/`?**
   - Currently it's a manual utility script
   - Consider adding to CI/CD pipeline or converting to pytest

2. **Is 21% overall coverage acceptable for this phase?**
   - Critical infrastructure files (main.py, handler_registration) are at 0%
   - Should these be tested before merging or acceptable as "manual test coverage"?

3. **What's the timeline for repository/persistence layer tests?**
   - Currently 0-35% coverage
   - Should be addressed before production deployment

4. **Are there other non-pytest testscripts that reference the old pattern?**
   - Search was limited to `.py` files
   - Check if there are shell scripts or other tooling that instantiate AppContainer

---

## Next Steps (Immediate)

1. **Commit 1:** Fix `testscripts/run_sync_jobs.py`
   - Update imports to use Services + handler_registration
   - Verify script executes without errors
   - Run manual test: `python testscripts/run_sync_jobs.py`

2. **Commit 2:** Add integration test for main.py
   - Create `tests/integration/test_app_startup.py`
   - Test Services initialization
   - Verify handler registration

3. **PR Check:** Ensure CI/CD runs pytest and coverage report
   - Confirm all 60 tests pass in CI
   - Flag any coverage regression

---

**Report Generated:** 2026-03-13 00:28 UTC
**Test Runner:** pytest 9.0.2 on Python 3.14.2
**Coverage Tool:** pytest-cov 7.0.0
