# Code Simplification: Dishka DI Migration

**Date:** 2026-03-13 | **Scope:** src/providers/, src/container.py, src/main.py, src/main_extensions.py

## Changes Summary

### 1. Merged `config_provider.py` + `messaging_provider.py` into `core_provider.py`
- **Before:** 2 files (12 + 17 LOC) with 2 classes for 3 trivial singletons
- **After:** 1 file (26 LOC) with `CoreProvider` class (Settings, EventBus, Mediator)
- **Why:** All three are foundational singletons with no async lifecycle; splitting them across 2 files added navigational overhead with no cohesion benefit
- **Deleted:** `config_provider.py`, `messaging_provider.py`

### 2. Simplified `src/container.py`
- Extracted `PROVIDERS` list with ordering comment ("later may depend on earlier")
- Compressed handler resolution loop into list comprehension
- Added "how to add a new provider" docstring

### 3. Cleaned up `src/main.py`
- Moved 6 deferred imports to top-level (they were always needed, deferral served no purpose)
- Removed intermediate variables (`database`, `cache`) -- assigned directly to `app.state`
- Removed redundant inline comments that restated the function names

### 4. Simplified `src/main_extensions.py`
- `register_health_checks`: Replaced closure wrappers with `functools.partial` (10 lines -> 3 lines)
- `start_background_jobs`: Early return for disabled jobs (reduced nesting)
- `ensure_all_indexes`: Extracted `_REPO_TYPES` list constant; loop -> comprehension
- Moved `Settings` and `Mediator` imports to top-level (were deferred unnecessarily)

### 5. Added onboarding comments
- `src/providers/__init__.py`: "Adding a new service" and "Adding a new CQRS handler" steps
- `src/container.py`: "Adding a new provider" steps
- `src/providers/core_provider.py`: Why these are grouped (no async lifecycle)

## File Count Change
- Providers: 7 files -> 6 files (net -1)

## Verification
- ruff check: 0 errors
- pyright: 0 errors, 0 warnings
- pytest: 60/60 passed
