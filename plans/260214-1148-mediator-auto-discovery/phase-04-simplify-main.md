# Phase 4: Simplify main.py Lifespan

**Priority:** High | **Status:** Pending

## Overview

Replace ~90 lines of manual handler imports + registration in `main.py` with 4 feature-level `register_handlers()` calls.

## Current State (lines 18-93 imports, lines 132-221 registration)

- 30+ handler/command/query imports from 5 features
- 27 individual `mediator.register(Type, Handler(...))` calls
- Tight coupling between main.py and every operation folder

## Target State

```python
# Imports: 4 lines instead of 30+
from src.features.market_data.register import register_handlers as register_market_data
from src.features.backtesting.register import register_handlers as register_backtesting
from src.features.strategy.register import register_handlers as register_strategy
from src.features.trading.register import register_handlers as register_trading

# Registration: 4 calls instead of 27
register_market_data(mediator, settings=settings, tv_provider=tv_provider, event_bus=event_bus)
register_strategy(mediator, strategy_engine=strategy_engine)
register_trading(mediator, order_manager=order_manager, position_tracker=position_tracker)
register_backtesting(mediator, event_bus=event_bus, strategy_engine=strategy_engine)
```

## Files to Modify

| File | Change |
|------|--------|
| `src/main.py` | Remove handler imports, replace with feature register imports + calls |

## Key Constraints

- **Keep non-handler setup unchanged**: DB connect, cache connect, indexes, jobs, strategy engine init, broker factory — all stays
- **Keep router includes unchanged**: `app.include_router(...)` stays as-is
- **Keep graceful shutdown unchanged**
- **Only handler registration changes**

## Implementation Steps

1. Remove all handler/command/query imports from main.py (lines 18-93)
2. Add 4 feature register imports
3. Replace 27 `mediator.register()` calls with 4 `register_handlers()` calls
4. Keep `set_mediator(mediator)` call for jobs module
5. Run `ruff check` + `pyright` to verify

## Before/After Comparison

**Before:** main.py ~310 LOC, 30+ handler imports
**After:** main.py ~200 LOC, 4 feature register imports

## Success Criteria

- [ ] main.py has no direct handler/command/query imports
- [ ] All 27 handlers still registered correctly
- [ ] `DuplicateHandlerError` fires if duplicate attempted
- [ ] Application starts and serves requests normally
- [ ] All existing tests pass
- [ ] `ruff check` + `pyright` clean
