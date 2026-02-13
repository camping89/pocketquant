# Code Review: Vertical Slice Restructure

**Reviewer:** code-reviewer | **Date:** 2026-02-13 | **Score: 9/10**

## Scope

- **Files changed:** 212 (2,728 insertions, 1,919 deletions)
- **Features reviewed:** strategy, backtesting, market_data, trading, risk
- **Focus:** Import consistency, `__init__.py` correctness, router patterns, CQRS compliance, orphaned files, circular imports

## Overall Assessment

Excellent restructure. All 5 features successfully migrated from the old `api/` + `handlers/` pattern to the canonical vertical slice pattern (operation folders at root, shared infra in `base/`, `router.py` aggregator). Zero broken imports, zero orphaned files, zero circular dependency risks. Clean CQRS separation in the new trading operation folders. The refactor is thorough and consistent.

## Critical Issues

None.

## High Priority

None.

## Medium Priority

### 1. `market_data/__init__.py` is just a docstring -- no re-exports

**File:** `src/features/market_data/__init__.py`

Unlike strategy, backtesting, and trading which have full `__init__.py` re-exports, market_data's init is a single docstring. This means `main.py` imports directly from sub-modules:

```python
from src.features.market_data.list_symbols import ListSymbolsQuery
from src.features.market_data.list_symbols.handler import ListSymbolsHandler
from src.features.market_data.ohlcv import GetOHLCVHandler, GetOHLCVQuery
from src.features.market_data.quotes import (...)
from src.features.market_data.status import (...)
from src.features.market_data.sync import (...)
```

Not blocking -- this works fine. But it's inconsistent with other features where a single `from src.features.X import ...` suffices. Consider adding a facade `__init__.py` for consistency if the number of imports in `main.py` grows.

### 2. `main.py` bypasses feature `__init__.py` for some imports

**File:** `src/main.py` lines 31-34, 94

```python
from src.features.backtesting.base.repository import BacktestRepository  # line 31
from src.features.market_data.base.jobs import register_sync_jobs, set_mediator  # line 32
from src.features.market_data.list_symbols.handler import ListSymbolsHandler  # line 34
from src.features.trading.base.repositories import OrderRepository, PositionRepository  # line 94
```

These reach into `base/` directly from `main.py`, bypassing the feature's `__init__.py` facade. Two patterns mixed: facade imports (most handlers) vs. direct deep imports (repositories, jobs). Consider re-exporting `BacktestRepository`, `OrderRepository`, `PositionRepository`, `register_sync_jobs`, `set_mediator` from the feature-level `__init__.py` or a dedicated setup module.

### 3. `backtesting/router.py` uses module-level attribute access (different pattern)

**File:** `src/features/backtesting/router.py`

```python
from src.features.backtesting import get_optimization, get_result, list_results, optimize, run
router.include_router(run.router)
```

Other routers import the `router` object directly from the route module:

```python
from src.features.strategy.get_all.route import router as get_strategies_router
router.include_router(get_strategies_router)
```

Both work. The backtesting pattern relies on `__init__.py` re-exporting `router`, which it does. Minor inconsistency -- pick one for future operations.

## Low Priority

### 4. `list_symbols/__init__.py` does not re-export `ListSymbolsHandler`

**File:** `src/features/market_data/list_symbols/__init__.py`

Only exports `ListSymbolsQuery`. The handler is imported directly in `main.py`:
```python
from src.features.market_data.list_symbols.handler import ListSymbolsHandler
```

All other operation `__init__.py` files export both query/command + handler. Trivial to fix.

### 5. Response model typing on route handlers

Some route handlers return `dict` without a response model (e.g., all 4 trading routes), while others use Pydantic response models (e.g., backtest run, strategy get_all). Not a bug, but typed response models improve OpenAPI docs.

## Edge Cases Found by Scout

- **No circular imports detected.** `base/` modules never import from operation folders. Cross-feature imports (strategy_engine -> risk, trading) use `TYPE_CHECKING` guards correctly.
- **No route path collisions.** All routes within each feature router have unique path patterns. No prefix shadowing between features.
- **No old path references.** Zero references to old `api/`, `handlers/`, `engine/`, `examples/`, `loader/`, `managers/`, `models/`, `repositories/`, `metrics/`, `optimizer/`, `repository/`, or `quote/` (singular) paths exist in `src/` or `tests/`.
- **All old folders deleted.** Confirmed on disk: no remnant `api/`, `handlers/`, etc. directories in any feature.

## Positive Observations

1. **Consistent vertical slice pattern.** Each operation is self-contained: `__init__.py`, `handler.py`, `query.py`/`command.py`, `route.py`. Easy to find, easy to add new operations.
2. **Clean `base/` separation.** Shared infra (models, managers, repositories, engine) correctly in `base/` subdirectory per feature. No upward dependencies.
3. **Proper TYPE_CHECKING usage.** Cross-feature type annotations guarded behind `if TYPE_CHECKING` to prevent circular imports (strategy_engine, run/handler).
4. **Router aggregation hierarchy.** market_data has 3-level hierarchy (feature router -> sub-feature routers -> operation routes) and it's well-structured.
5. **CQRS separation clean.** Trading operations properly split: queries (list_orders, get_order, list_positions, get_position) with `query.py`, no commands yet (appropriate -- order creation goes through strategy engine).
6. **All `__init__.py` files have `__all__` declarations.** Good for IDE tooling and explicit public API surface.
7. **All Python files compile without errors.**

## Recommended Actions

1. **(Medium)** Add facade re-exports to `market_data/__init__.py` for parity with other features
2. **(Medium)** Re-export infrastructure items (`BacktestRepository`, `OrderRepository`, `PositionRepository`, job helpers) from feature-level `__init__.py` to keep `main.py` imports consistent
3. **(Low)** Add `ListSymbolsHandler` to `list_symbols/__init__.py` re-exports
4. **(Low)** Standardize router import pattern -- prefer direct route import over module attribute access, or vice versa
5. **(Low)** Add Pydantic response models to trading routes for OpenAPI completeness

## Metrics

- **Syntax Errors:** 0
- **Orphaned Files:** 0
- **Circular Import Risks:** 0
- **Import Consistency:** ~90% (market_data facade + a few deep imports in main.py)
- **CQRS Compliance:** 100% (all operations follow command/query + handler + route pattern)
- **Router Pattern Consistency:** ~85% (backtesting uses module attribute access; rest use direct import)

## Unresolved Questions

- Should `market_data` get a full `__init__.py` facade now or defer until the import list stabilizes?
- Should `risk` feature eventually get a `router.py` and route endpoints (currently handler-only, no API)?
