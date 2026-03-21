# Code Review: Migration Doubts Cleanup

**Date:** 2026-03-21
**Branch:** `feat/strategy-init` (commit `d86c950`)
**Reviewer:** code-reviewer agent

## Scope

- **Files changed:** ~56 (excluding session-state)
- **LOC:** +166 / -1988 (net deletion -- good)
- **Focus:** 5-phase migration cleanup: dead coupling removal, repo relocation, DI import fixes, config discovery, test migration

## Overall Assessment

Clean, well-executed cleanup. All 5 phases correctly implemented. No stale imports remain in code. Import linter rules properly tightened (removed `ignore_imports`). The changes are straightforward moves and deletions with minimal logic changes, reducing risk.

---

## Critical Issues

None found.

---

## High Priority

### H1. `_find_project_root()` runs at module import time -- fails before app starts if CWD is wrong

**File:** `packages/pocketquant-core/src/pocketquant/core/config.py:24`

```python
_ENV_FILE = _find_project_root() / ".env"  # executes on import
```

This module-level call means `_find_project_root()` runs the first time `config.py` is imported. If CWD is not inside the workspace (e.g., running from a Docker entrypoint, CI runner, or IDE with different working dir) AND `POCKETQUANT_ROOT` is not set, it raises `FileNotFoundError` at import time -- before any application code can catch it.

**Impact:** Hard crash during import in containerized/CI environments.

**Recommendations:**
1. Consider lazy evaluation via `@lru_cache` on a function that returns the path, called only from `get_settings()`. This defers the error to first use, not import time.
2. Alternatively, document `POCKETQUANT_ROOT` as required env var for non-standard deployments (Docker, CI).
3. The string-based search (`"[tool.uv.workspace]" in pyproject.read_text()`) is fragile -- a comment containing that substring would match. Consider using `tomllib.loads()` for proper TOML parsing. Low probability but worth noting.

### H2. `conftest.py` passes `debug=True` to `Settings` -- silently ignored

**File:** `packages/pocketquant-core/tests/conftest.py:18`

```python
Settings(
    ...
    debug=True,  # Settings has no 'debug' field
)
```

`Settings` uses `extra="ignore"`, so this doesn't crash, but it means tests think they have debug mode enabled when they don't. If a `debug` field is ever added, this test config would silently start affecting behavior.

**Impact:** Low (no current breakage), but misleading test setup.

**Recommendation:** Remove `debug=True` from conftest or add `debug` field to `Settings` if needed.

---

## Medium Priority

### M1. `StrategyAppService` uses `TYPE_CHECKING` guard for same-package imports (pre-existing)

**File:** `packages/pocketquant-trading/src/pocketquant/trading/app_services/strategy_app_service.py:17-20`

```python
if TYPE_CHECKING:
    from pocketquant.trading.app_services.order_app_service import OrderAppService
    from pocketquant.trading.app_services.position_app_service import PositionAppService
    from pocketquant.trading.handlers.risk.check_risk.handler import RiskCheckHandler
```

These are same-package imports behind `TYPE_CHECKING`. This is fine because:
- Dishka doesn't auto-resolve `StrategyAppService.__init__` -- `TradingProvider.get_strategy_engine()` constructs it manually with keyword args
- The guard prevents circular imports within the trading package

However, if anyone later switches to `provide(StrategyAppService, scope=Scope.APP)` (dishka auto-resolution), it will silently fail at runtime because the type hints won't be available.

**Recommendation:** Add a comment on the `TYPE_CHECKING` block: `# Must remain guarded -- circular import. DI uses manual factory in trading.py`

### M2. Parameter rename consistency -- DI factory method names not updated

**File:** `packages/pocketquant-api/src/pocketquant/api/di/trading.py:24,32`

```python
async def get_order_manager(...)   # Still says "order_manager"
async def get_position_tracker(...)  # Still says "position_tracker"
```

The commit renamed all handler/service attributes from `order_manager` -> `order_app_service` and `position_tracker` -> `position_app_service`, but the DI factory method names were not updated. Not a bug (dishka matches by return type, not method name), but inconsistent.

**Recommendation:** Rename to `get_order_app_service` and `get_position_app_service` for consistency.

### M3. `pyproject.read_text()` in config may fail on non-UTF8 systems

**File:** `packages/pocketquant-core/src/pocketquant/core/config.py:15`

```python
if pyproject.exists() and "[tool.uv.workspace]" in pyproject.read_text():
```

`read_text()` without explicit `encoding` uses system default encoding. On some Windows systems this is `cp1252`, not `utf-8`. TOML files are always UTF-8. If any path component contains non-ASCII, or the file has non-ASCII content, this could fail.

**Recommendation:** `pyproject.read_text(encoding="utf-8")`

---

## Low Priority

### L1. Test scaffold conftest files are empty stubs

The `conftest.py` files for backtest, trading, and api packages contain only a docstring. Fine for now but worth populating as tests are added (shared fixtures for DB mocking, etc.).

### L2. `test_domain_purity.py` uses relative path traversal

**File:** `packages/pocketquant-core/tests/unit/domain/test_domain_purity.py:22-24`

```python
domain_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "src", "pocketquant", "core", "domain"
)
```

This 3-level parent traversal is correct for the current layout but fragile if the test file moves. Consider using a project-root discovery mechanism or `importlib.resources`.

---

## Edge Cases Found by Scout

1. **No stale `from pocketquant.core.persistence.repositories.order_repository` imports in code** -- only in plan docs (expected)
2. **No stale `self.state`, `self.order_manager`, `self.position_tracker`, `self._engine` attributes remain** -- all renamed correctly
3. **No `StrategyAppService` references in backtest package** -- fully decoupled
4. **`ignore_imports` properly removed from pyproject.toml** -- import linter contract is now strict
5. **Old `tests/` directory fully deleted** -- no orphaned files
6. **`pyproject.toml` testpaths correctly lists all 4 package test directories**
7. **Moved repos (`order_repository.py`, `position_repository.py`) correctly import from `pocketquant.core` for base classes** -- dependency direction is correct (trading -> core)

---

## Positive Observations

1. **Net code deletion (-1800+ lines)** -- removing dead coupling, old test copies, and `ignore_imports` hacks
2. **Import linter enforcement tightened** -- backtest no longer needs exemptions to import from trading
3. **Constructor parameter naming standardized** -- `order_manager` -> `order_app_service` consistently across all handlers
4. **Config discovery is pragmatic** -- `_find_project_root()` with env var fallback handles real-world deployment scenarios
5. **Migration notes doc properly updated** with resolution status for all 7 items
6. **Clean `trading/persistence/__init__.py`** with proper `__all__` exports

---

## Recommended Actions

1. **[H1]** Add `encoding="utf-8"` to `pyproject.read_text()` and consider lazy-loading `_ENV_FILE`
2. **[H2]** Remove `debug=True` from test conftest
3. **[M2]** Rename DI factory methods for consistency (optional, non-breaking)
4. **[M1]** Add comment on TYPE_CHECKING guard to prevent future DI breakage

---

## Metrics

- **Stale import references:** 0 (in code; plan docs have old paths, expected)
- **Import linter exemptions removed:** 4
- **Test files migrated:** 7 (all under `packages/pocketquant-core/tests/`)
- **Tests passing:** 52 (per migration notes)

---

## Unresolved Questions

1. Is `POCKETQUANT_ROOT` documented anywhere for Docker/CI deployments? (Not in `.env.example` or deployment guide from what I see)
2. Should the 3 empty scaffold `conftest.py` files share common fixtures (e.g., `settings`, `event_bus`) via a workspace-level conftest?
