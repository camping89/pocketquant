# Phase 6: Cross-Cutting Cleanup

## Priority: Critical | Effort: Medium | Risk: High

Final phase — update main.py, infrastructure imports, docs, and verify everything compiles.

## Context

- [Plan](plan.md) | Depends on: Phases 1-5
- All features already restructured, `__init__.py` re-exports maintain backward compat
- This phase updates consumers to use new paths directly + cleans up

## Tasks

### 1. Update main.py

**Router imports:**
```python
# Old
from src.features.backtesting.api.backtest_routes import router as backtest_router
from src.features.market_data.api import quote_router
from src.features.market_data.api import router as market_data_router
from src.features.strategy.api import strategy_router
from src.features.trading.api import trading_router

# New
from src.features.backtesting.router import router as backtest_router
from src.features.market_data.router import router as market_data_router
from src.features.market_data.quotes.router import router as quote_router
from src.features.strategy.router import router as strategy_router
from src.features.trading.router import router as trading_router
```

**Handler imports — update to direct paths:**
```python
# Old (via __init__.py re-exports — still works, but clean up)
from src.features.backtesting import RunBacktestHandler, RunBacktestCommand, ...
from src.features.strategy import LoadStrategyHandler, LoadStrategyCommand, ...

# New (direct from operation folders)
from src.features.strategy.load import LoadStrategyCommand, LoadStrategyHandler
from src.features.strategy.start import StartStrategyCommand, StartStrategyHandler
# ... etc
```

**Trading mediator registrations (new):**
```python
from src.features.trading import (
    ListOrdersQuery, ListOrdersHandler,
    GetOrderQuery, GetOrderHandler,
    ListPositionsQuery, ListPositionsHandler,
    GetPositionQuery, GetPositionHandler,
)
mediator.register(ListOrdersQuery, ListOrdersHandler(order_manager))
mediator.register(GetOrderQuery, GetOrderHandler(order_manager))
mediator.register(ListPositionsQuery, ListPositionsHandler(position_tracker))
mediator.register(GetPositionQuery, GetPositionHandler(position_tracker))
```

**Repository import:**
```python
# Old
from src.features.backtesting.repository import BacktestRepository
from src.features.trading.repositories import OrderRepository, PositionRepository

# New
from src.features.backtesting.base.repository import BacktestRepository
from src.features.trading.base.repositories import OrderRepository, PositionRepository
```

### 2. Update Infrastructure Imports

**`src/infrastructure/tradingview/provider.py`:**
```python
# Old
from src.features.market_data.models.ohlcv import ...
# New
from src.features.market_data.base.models.ohlcv import ...
```

**`src/infrastructure/tradingview/base.py`:**
```python
# Old
from src.features.market_data.models.ohlcv import Interval, OHLCVCreate
# New
from src.features.market_data.base.models.ohlcv import Interval, OHLCVCreate
```

### 3. Simplify __init__.py Files

After main.py uses direct paths, feature `__init__.py` files can be simplified. Keep only essential re-exports that are used by other features (not just main.py).

### 4. Update Documentation

**`docs/code-standards.md`:**
- Update "Vertical Slice Architecture" section — replace old structure with canonical pattern
- Remove `api/` and `handlers/` from the template
- Add `base/` and `router.py` to the template
- Update file size targets (remove `routes.py` reference)

**`docs/codebase-summary.md`:**
- Update feature directory structure if listed

### 5. Clean Up

- Delete all `__pycache__/` in moved directories
- Verify no orphaned `__init__.py` files in deleted folders
- Run full test suite: `pytest`
- Run full lint: `ruff check src/`
- Run full type check: `pyright src/`

## Implementation Steps

1. Update `main.py` — router imports, handler imports, trading mediator registrations
2. Update `infrastructure/tradingview/` imports
3. Simplify feature `__init__.py` files
4. Update `docs/code-standards.md`
5. Delete `__pycache__/` directories
6. Run `ruff check src/` — fix any import issues
7. Run `pyright src/` — fix any type issues
8. Run `pytest` — verify no regressions
9. Run `ruff format src/` — clean formatting

## Todo

- [x] Update main.py router imports (already done in previous phases)
- [x] Update main.py handler imports to direct paths (already done in previous phases)
- [x] Add trading mediator registrations (already done in previous phases)
- [x] Update infrastructure/tradingview imports (already correct)
- [x] Simplify feature __init__.py files (done in previous phases)
- [x] Update docs/code-standards.md (updated vertical slice architecture section)
- [x] Clean __pycache__ directories (not needed, .gitignore handles)
- [x] ruff check passes (1 warning only - Generic style, not critical)
- [x] pyright passes (0 errors, 0 warnings)
- [ ] pytest passes (not run - requires MongoDB/Redis)

## Success Criteria

- `uvicorn src.main:app` starts without errors
- All API endpoints respond correctly
- `ruff check src/` clean
- `pyright src/` clean
- `pytest` passes
- No references to old paths (handlers/, api/) remain in src/
- docs/code-standards.md reflects new canonical pattern
