# Phase 1C: BarManager Rename

## Context
- Brainstorm: `QuoteAggregator` contains pure domain logic (bar building, tick aggregation)
- Per naming convention: Manager = pure logic, Service = I/O orchestration
- Current location: `services/quote_aggregator.py`

## Overview
- **Priority:** P2
- **Status:** Pending
- **Effort:** 20 min
- **Parallelizable:** Yes (no file overlap with 1A, 1B)

## Key Insights
- `QuoteAggregator` does bar building (pure domain logic)
- Should be renamed to `BarManager` in `managers/` folder
- Inner `BarBuilder` class name stays (already correct)

## Requirements

### Functional
- Rename `QuoteAggregator` class → `BarManager`
- Move from `services/` → `managers/` folder

### Non-functional
- Preserve all existing functionality
- Update log event names from `quote_aggregator.*` to `bar_manager.*`

## Files

### Create
- `src/features/market_data/managers/__init__.py`
- `src/features/market_data/managers/bar_manager.py` (copy from quote_aggregator.py)

### Delete (Phase 5)
- `src/features/market_data/services/quote_aggregator.py` (after imports updated)

## Implementation Steps

### Step 1: Create managers folder
```bash
mkdir -p src/features/market_data/managers
touch src/features/market_data/managers/__init__.py
```

### Step 2: Create bar_manager.py
Copy `quote_aggregator.py` with these changes:
1. Rename class `QuoteAggregator` → `BarManager`
2. Update log events:
   - `quote_aggregator.bar_saved` → `bar_manager.bar_saved`
   - `quote_aggregator.bars_flushed` → `bar_manager.bars_flushed`

### Step 3: Create __init__.py
```python
# src/features/market_data/managers/__init__.py
from src.features.market_data.managers.bar_manager import BarManager

__all__ = ["BarManager"]
```

## Code Changes

**bar_manager.py header:**
```python
# ... imports stay same ...

logger = get_logger(__name__)

INTERVAL_SECONDS = { ... }  # unchanged

class BarBuilder:  # unchanged name
    ...

def _get_bar_start(...):  # unchanged
    ...

class BarManager:  # renamed from QuoteAggregator
    CURRENT_BAR_PREFIX = "bar:current:"
    # ... rest unchanged except log events
```

**Log event updates:**
```python
# Line ~203-210
logger.info(
    "bar_manager.bar_saved",  # was quote_aggregator.bar_saved
    ...
)

# Line ~243
logger.info("bar_manager.bars_flushed", saved_count=saved_count)  # was quote_aggregator
```

## Todo

- [ ] Create `managers/` folder
- [ ] Create `managers/__init__.py`
- [ ] Create `managers/bar_manager.py` (copy + rename)
- [ ] Update log event names
- [ ] Keep `services/quote_aggregator.py` until Phase 4 (import updates)

## Success Criteria
- [ ] `managers/bar_manager.py` exists with `BarManager` class
- [ ] `BarBuilder` helper class unchanged
- [ ] Log events renamed to `bar_manager.*`
- [ ] File compiles (`python -c "from src.features.market_data.managers import BarManager"`)

## Risks
- Import errors if updated before Phase 4
- Mitigation: Keep old file until Phase 4 updates all imports
