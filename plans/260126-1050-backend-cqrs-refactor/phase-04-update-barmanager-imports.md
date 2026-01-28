# Phase 4: Update BarManager Imports

## Context
- Phase 1C created `managers/bar_manager.py` with `BarManager` class
- Old `services/quote_aggregator.py` still exists for backward compat
- Now update all imports to use new location

## Overview
- **Priority:** P2
- **Status:** Pending
- **Effort:** 15 min
- **Depends on:** Phase 1C, 2, 3 completed

## Key Insights
- Only 2 files import QuoteAggregator
- Simple find-replace operation
- Delete old file after imports updated

## Requirements

### Functional
- Update all imports from `services.quote_aggregator.QuoteAggregator` → `managers.bar_manager.BarManager`
- Rename variable names from `aggregator` to `bar_manager` (optional, for clarity)

### Non-functional
- No behavior change
- Clean up old file

## Files

### Modify
- `src/features/market_data/services/quote_service.py`
- `src/features/market_data/api/quote_routes.py`

### Delete
- `src/features/market_data/services/quote_aggregator.py`

## Implementation Steps

### Step 1: Update quote_service.py

**Current:**
```python
from src.features.market_data.services.quote_aggregator import QuoteAggregator
# ...
self._aggregator = QuoteAggregator()
# ...
def get_aggregator(self) -> QuoteAggregator:
```

**Replace with:**
```python
from src.features.market_data.managers.bar_manager import BarManager
# ...
self._bar_manager = BarManager()
# ...
def get_bar_manager(self) -> BarManager:
    return self._bar_manager
```

**Update internal calls:**
- `self._aggregator.add_tick(tick)` → `self._bar_manager.add_tick(tick)`
- Keep `get_aggregator()` as alias for backward compat (optional)

### Step 2: Update quote_routes.py

**Current:**
```python
aggregator = service.get_aggregator()
bar = await aggregator.get_current_bar(symbol, exchange, interval)
# ...
aggregator = service.get_aggregator()
saved_count = await aggregator.flush_all_bars()
# ...
active_symbols=aggregator.active_symbols,
```

**Replace with:**
```python
bar_manager = service.get_bar_manager()
bar = await bar_manager.get_current_bar(symbol, exchange, interval)
# ...
bar_manager = service.get_bar_manager()
saved_count = await bar_manager.flush_all_bars()
# ...
active_symbols=bar_manager.active_symbols,
```

### Step 3: Delete old file
```bash
rm src/features/market_data/services/quote_aggregator.py
```

## Todo

- [ ] Update quote_service.py imports and class attribute
- [ ] Add `get_bar_manager()` method (keep `get_aggregator()` as alias if needed)
- [ ] Update quote_routes.py variable names
- [ ] Delete old `services/quote_aggregator.py`
- [ ] Run tests

## Success Criteria
- [ ] No imports from `services/quote_aggregator`
- [ ] `quote_aggregator.py` deleted
- [ ] All quote endpoints work
- [ ] All tests pass

## Risks
- Breaking change if external code imports QuoteAggregator
- Mitigation: Internal only, no public API change
