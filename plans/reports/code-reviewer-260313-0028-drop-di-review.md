# Code Review: Drop dependency-injector Refactor

**Date:** 2026-03-13
**Scope:** `src/services.py`, `src/dependencies.py`, `src/handler_registration.py`, `src/main.py`, `src/main_extensions.py`, `pyproject.toml`
**Deleted:** `src/container.py`, `src/common/mediator/dependencies.py`, `src/features/market_data/quotes/dependencies.py`

## Overall Assessment

Clean, well-structured refactor. The frozen dataclass registry + explicit handler construction is a significant improvement over the DI container's string-based wiring. Constructor args verified correct against all handler `__init__` signatures. No dangling imports to deleted files. Two shutdown safety bugs need fixing before merge.

## Critical Issues

### 1. Shutdown `finally` block has `UnboundLocalError` risk

**File:** `src/main.py:162-170`

The `finally` block references `strategy_engine`, `job_scheduler`, `cache`, `database`. If init fails *after* the `try` starts but *before* `strategy_engine` is created (e.g., `order_manager.load_pending_orders()` fails at line 99), the `finally` block will crash with `UnboundLocalError` on `strategy_engine`.

**Fix:** Initialize sentinel values before the `try`, or guard each shutdown call:

```python
# Option A: sentinels before try
strategy_engine = None
job_scheduler = None

try:
    ...
finally:
    if strategy_engine:
        await strategy_engine.stop()
    if job_scheduler and settings.enable_jobs:
        job_scheduler.shutdown(wait=True)
    await cache.disconnect()
    await database.disconnect()
```

### 2. `database` leaks if `cache.connect()` fails

**File:** `src/main.py:61-64`

`database.connect()` and `cache.connect()` are *outside* the `try` block. If `cache.connect()` raises, `database` is connected but never disconnected. The exception propagates up to FastAPI, skipping the `finally` entirely.

**Fix:** Wrap persistence init in the `try` or use a nested try:

```python
database = Database()
await database.connect(settings)
try:
    cache = Cache()
    await cache.connect(settings)
    try:
        ...
    finally:
        await cache.disconnect()
finally:
    await database.disconnect()
```

Or simpler -- move lines 61-64 inside the existing `try` and add guards in `finally`.

### 3. `handle_startup_failure()` calls `os._exit(1)` -- skips `finally`

**File:** `src/main.py:160-161`, `src/main_extensions.py:77`

The `except` clause calls `handle_startup_failure(e)` which does `os._exit(1)`. This kills the process *before* the `finally` block runs, so DB/cache connections leak on startup failure.

**Fix:** Either (a) let `handle_startup_failure` just log/print and then `raise` so `finally` runs, or (b) move cleanup into the `except` block before calling `os._exit`.

## High Priority

### 4. `uv.lock` still contains `dependency-injector`

`dependency-injector` was removed from `pyproject.toml` but its entry remains in `uv.lock`. Run `uv lock` to regenerate.

### 5. `QuoteServiceDep` and `ServicesDep` are unused

**File:** `src/dependencies.py:29-30`

Defined but not imported anywhere in `src/features/`. All routes use `Annotated[Mediator, Depends(get_mediator)]` inline. Either remove the unused aliases or migrate routes to use them for consistency. Minor dead code but worth cleaning up.

## Medium Priority

### 6. `except` catches all `Exception` silently

**File:** `src/main.py:160`

The bare `except Exception` + `os._exit(1)` swallows the original traceback from Python's perspective. The rich panel prints the message but doesn't preserve the full stack. Consider `logger.exception()` before the panel, or use `raise` after printing.

### 7. Handler count comment may drift

**File:** `src/handler_registration.py:58-94`

Comments say "Market data (13)", "Trading (4)", "Strategy (5)", "Backtesting (5)" = 27 total. This is correct today but will silently drift as handlers are added. Consider an assertion:

```python
count = registry.register_all(services.mediator, handlers)
assert count == len(handlers), f"Registration mismatch: {count} != {len(handlers)}"
```

The `register_all` already returns a count; this just makes it fail-fast.

### 8. `BarManager` constructed without `intervals` param

**File:** `src/main.py:92`

`BarManager.__init__` accepts optional `intervals: list[Interval] | None = None` which defaults to a built-in list. The old container also didn't pass it. This is fine, but worth noting the implicit coupling to the hardcoded default.

## Low Priority

### 9. Inline imports in lifespan function

**File:** `src/main.py:25-56`

32 import lines inside the function. The docstring says "keep module-level imports lightweight" but this is the app's main module -- it won't be imported by anything else. Moving these to module level would improve readability and let static analyzers catch issues earlier. Not blocking.

### 10. `app.state.cache` / `app.state.database` duplicated on state

**File:** `src/main.py:149-150`

These are set separately from `app.state.services` for middleware hot-path access. This creates two paths to the same object (`app.state.cache` and `app.state.services.cache`). Acceptable for performance, but document the reason with a comment (already has one -- good).

## Positive Observations

- **Constructor wiring verified correct** -- all 27 handler signatures match the args in `handler_registration.py`
- **No dangling imports** -- zero references to `src.container`, `src.common.mediator.dependencies`, or `src.features.market_data.quotes.dependencies` remain in `src/`
- **Frozen dataclass** prevents accidental mutation of the service registry
- **Single `dependencies.py`** file centralizes all DI -- easy to find and audit
- **Explicit construction** makes the dependency graph visible and debuggable
- **`dependency-injector` removed from `pyproject.toml`** dependencies

## Recommended Actions (Priority Order)

1. **Fix shutdown safety** (issues 1-3): guard `finally` against unbound locals, wrap persistence init in try, decide `os._exit` vs `raise` semantics
2. **Run `uv lock`** to regenerate lockfile without dependency-injector
3. **Remove unused `QuoteServiceDep`/`ServicesDep`** or adopt them consistently
4. **Add `logger.exception()`** before `handle_startup_failure` to preserve full traceback

## Unresolved Questions

- Should `handle_startup_failure` use `os._exit(1)` or `raise`? `os._exit` guarantees no half-started server, but skips cleanup. A `raise` lets `finally` run but risks uvicorn catching and continuing. Suggest: do cleanup first, then `os._exit`.
- Should routes migrate to the `MediatorDep` type alias instead of inline `Annotated[Mediator, Depends(get_mediator)]`? Would reduce boilerplate across ~25 route files.
