# Phase 3: Update Routes to FromDishka

## Context Links
- [Phase 2: Migrate Lifespan](./phase-02-migrate-lifespan.md) — must be complete first
- [Current dependencies.py](../../src/dependencies.py) — Depends() functions being replaced
- [Route grep results](#affected-routes) — 27 route files + 2 system routes

## Overview
- **Priority**: P2
- **Status**: pending
- **Description**: Replace `Annotated[Mediator, Depends(get_mediator)]` with `FromDishka[Mediator]` across all 27 route files. Replace `Annotated[QuoteService, Depends(get_quote_service)]` in 1 route file.

## Key Insights

1. **DishkaRoute vs @inject**: Two approaches.
   - `DishkaRoute`: Set `route_class=DishkaRoute` on router — all routes auto-inject `FromDishka[]` params. No decorator needed.
   - `@inject`: Decorator per route function. More explicit but repetitive.
   - **Recommendation**: Use `DishkaRoute` on parent aggregate routers (backtest, trading, strategy, market_data, quotes). Simpler and consistent.

2. **Import changes per route file**:
   - Remove: `from src.dependencies import get_mediator` (or `get_quote_service`)
   - Remove: `from fastapi import Depends`
   - Add: `from dishka import FromDishka`
   - Change param: `mediator: Annotated[Mediator, Depends(get_mediator)]` → `mediator: FromDishka[Mediator]`

3. **Scope**: Routes get REQUEST-scoped container automatically. Mediator is APP-scoped so dishka returns the cached singleton.

## Affected Routes

### Pattern A: `Annotated[Mediator, Depends(get_mediator)]` (26 files)

| Feature | File |
|---------|------|
| backtesting | `get_optimization/route.py`, `get_result/route.py`, `list_results/route.py`, `optimize/route.py`, `run/route.py` |
| market_data | `list_symbols/route.py`, `ohlcv/get_ohlcv/route.py` |
| market_data/quotes | `get_all/route.py`, `get_latest/route.py`, `start_feed/route.py`, `stop_feed/route.py`, `subscribe/route.py`, `unsubscribe/route.py` |
| market_data/status | `get_quote_service_status/route.py`, `get_symbol_sync_status/route.py`, `get_sync_status/route.py` |
| market_data/sync | `sync_one/route.py` (2 endpoints), `sync_bulk/router.py` |
| strategy | `get_all/route.py`, `get_one/route.py`, `load/route.py`, `start/route.py`, `stop/route.py` |
| trading | `get_order/route.py`, `get_position/route.py`, `list_orders/route.py`, `list_positions/route.py` |

### Pattern B: `Annotated[QuoteService, Depends(get_quote_service)]` (1 file)

| Feature | File |
|---------|------|
| market_data/quotes | `get_current_bar/route.py` |

## Implementation Steps

### 1. Set DishkaRoute on parent routers

Update the 5 parent aggregate router files to use `DishkaRoute`:

**`src/features/backtesting/router.py`**:
```python
from dishka.integrations.fastapi import DishkaRoute
router = APIRouter(prefix="/backtest", tags=["backtest"], route_class=DishkaRoute)
```

**`src/features/trading/router.py`**:
```python
from dishka.integrations.fastapi import DishkaRoute
router = APIRouter(prefix="/trading", tags=["trading"], route_class=DishkaRoute)
```

**`src/features/strategy/router.py`**:
```python
from dishka.integrations.fastapi import DishkaRoute
router = APIRouter(prefix="/strategies", tags=["strategies"], route_class=DishkaRoute)
```

**`src/features/market_data/router.py`**: Parent for ohlcv, sync, status, list_symbols
```python
from dishka.integrations.fastapi import DishkaRoute
router = APIRouter(prefix="/market-data", tags=["market-data"], route_class=DishkaRoute)
```

**`src/features/market_data/quotes/router.py`**: Parent for quotes operations
```python
from dishka.integrations.fastapi import DishkaRoute
router = APIRouter(prefix="/quotes", tags=["Real-time Quotes"], route_class=DishkaRoute)
```

**IMPORTANT**: Verify that `DishkaRoute` set on parent router propagates to child sub-routers included via `include_router()`. If not, set `route_class=DishkaRoute` on each child router too. Check dishka docs.

**FALLBACK**: If `DishkaRoute` doesn't propagate, use `@inject` decorator on each route function instead. More verbose but guaranteed to work.

### 2. Update route files (Pattern A — Mediator)

For each of the 26 route files, make these changes:

**Before**:
```python
from typing import Annotated
from fastapi import APIRouter, Depends
from src.common.mediator import Mediator
from src.dependencies import get_mediator

@router.post("/run")
async def run_backtest(
    cmd: RunBacktestCommand,
    mediator: Annotated[Mediator, Depends(get_mediator)],
) -> dict:
    result = await mediator.send(cmd)
    ...
```

**After**:
```python
from fastapi import APIRouter
from dishka import FromDishka
from src.common.mediator import Mediator

@router.post("/run")
async def run_backtest(
    cmd: RunBacktestCommand,
    mediator: FromDishka[Mediator],
) -> dict:
    result = await mediator.send(cmd)
    ...
```

Changes:
- Remove `Annotated` import (if only used for DI)
- Remove `Depends` import (if only used for DI — keep if used for other things like `Query`)
- Remove `from src.dependencies import get_mediator`
- Add `from dishka import FromDishka`
- Change param type to `FromDishka[Mediator]`

### 3. Update route file (Pattern B — QuoteService)

**`src/features/market_data/quotes/get_current_bar/route.py`**:

**Before**:
```python
from src.dependencies import get_quote_service
quote_service: Annotated[QuoteService, Depends(get_quote_service)],
```

**After**:
```python
from dishka import FromDishka
quote_service: FromDishka[QuoteService],
```

### 4. Update sync_bulk router

`src/features/market_data/sync/sync_bulk/router.py` — this file defines its own router (not using a parent). Either:
- Set `route_class=DishkaRoute` on it, or
- Use `@inject` decorator

### 5. Batch execution strategy

Use search-and-replace across the codebase:
1. Replace `from src.dependencies import get_mediator` → `from dishka import FromDishka` (all route files)
2. Replace `Annotated[Mediator, Depends(get_mediator)]` → `FromDishka[Mediator]`
3. Clean up unused `Depends`, `Annotated` imports per file
4. Handle the 1 QuoteService route separately

## Todo List

- [ ] Set `DishkaRoute` on 5 parent aggregate routers
- [ ] Verify DishkaRoute propagation to child routers
- [ ] Update 26 Mediator route files
- [ ] Update 1 QuoteService route file
- [ ] Update sync_bulk router
- [ ] Clean up unused imports in all route files
- [ ] Run `ruff check src/features/` — zero errors
- [ ] Run `pyright src/features/` — zero errors
- [ ] Start app and hit 2-3 endpoints to verify injection works

## Success Criteria

- All route files use `FromDishka[Mediator]` or `FromDishka[QuoteService]`
- No imports from `src.dependencies` remain in route files
- App starts and routes return correct responses
- `ruff check` and `pyright` pass on all modified files

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| DishkaRoute doesn't propagate to sub-routers | Routes return 500 (missing injection) | Test first; fall back to @inject per route |
| FastAPI Query/Path params conflict with FromDishka | Route param parsing breaks | FromDishka uses different mechanism; shouldn't conflict |
| Some routes use both Depends(get_mediator) and other Depends | Import cleanup may remove needed Depends | Check each file; keep Depends if used for Query/Body/etc. |
