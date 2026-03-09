# Phase 5: Verify & Cleanup

## Overview
- **Priority:** Medium (final quality gate)
- **Status:** completed
- **Effort:** 30min

Verify zero Pydantic imports remain in domain layer. Run full lint, type check, tests. Clean up unused imports.

## Verification Checklist

### 1. Zero Pydantic in Domain

```bash
# Must return ZERO results
rg "pydantic" src/domain/
```

Expected: no matches. Every `from pydantic import ...` should be removed from domain files.

### 2. Domain Purity Test

```bash
# Existing AST-based test that checks domain has no I/O imports
pytest tests/test_domain_purity.py -v
```

Pydantic is not I/O, but removing it further purifies domain. Verify test still passes.

### 3. Lint & Type Check

```bash
ruff check src/domain/
ruff format --check src/domain/
pyright src/domain/
```

### 4. Full Test Suite

```bash
pytest -x --tb=short
```

### 5. Import Cleanup

Files that may have leftover Pydantic imports after conversion:

| File | Expected State |
|------|---------------|
| `src/domain/shared/domain_event.py` | `from dataclasses import dataclass, field` only |
| `src/domain/shared/value_objects.py` | `from dataclasses import dataclass` + `from enum import Enum` |
| `src/domain/order/aggregate.py` | `from dataclasses import dataclass, field` |
| `src/domain/order/order_event.py` | `from dataclasses import dataclass` |
| `src/domain/order/value_objects.py` | `from enum import Enum` only (no dataclass, no pydantic) |
| `src/domain/position/aggregate.py` | `from dataclasses import dataclass, field` |
| `src/domain/position/position_event.py` | `from dataclasses import dataclass` |
| `src/domain/position/value_objects.py` | `from dataclasses import dataclass` + `from enum import Enum` |
| `src/domain/quote/aggregate.py` | `from dataclasses import dataclass, field` |
| `src/domain/quote/quote_event.py` | `from dataclasses import dataclass` |
| `src/domain/quote/value_objects.py` | `from dataclasses import dataclass` |
| `src/domain/ohlcv/aggregate.py` | `from dataclasses import dataclass, field` |
| `src/domain/ohlcv/ohlcv_event.py` | `from dataclasses import dataclass` |
| `src/domain/ohlcv/value_objects.py` | `from dataclasses import dataclass` |
| `src/domain/risk/value_objects.py` | `from dataclasses import dataclass` + `from enum import Enum` |
| `src/domain/strategy/value_objects.py` | `from dataclasses import dataclass, field` (already partial) |
| `src/domain/strategy/strategy_event.py` | `from dataclasses import dataclass` |

### 6. Simplification Opportunities

During refactor, look for:
- [ ] Aggregates with inconsistent event collection (`collect_events` vs `get_uncommitted_events` + `clear_events`) -- standardize to one pattern
- [ ] Remove `from __future__ import annotations` from files that no longer need it (was needed for Pydantic forward refs; dataclass may not need it -- keep if using `ClassName` in return types within the class)
- [ ] SymbolAggregate `deactivate()`/`activate()` recreates entire SymbolInfo -- could use `dataclasses.replace()` instead

**SymbolAggregate simplification with `replace()`:**
```python
# BEFORE: manually reconstructing frozen SymbolInfo
def deactivate(self) -> None:
    if self.info:
        self.info = SymbolInfo(
            code=self.info.code, exchange=self.info.exchange,
            name=self.info.name, asset_type=self.info.asset_type,
            is_active=False,
        )

# AFTER: using dataclasses.replace() on frozen VO
from dataclasses import replace
def deactivate(self) -> None:
    if self.info:
        self.info = replace(self.info, is_active=False)
```

### 7. Event Collection Standardization

Currently two patterns exist:

| Pattern | Used By |
|---------|---------|
| `collect_events()` (returns + clears) | OrderAggregate, PositionAggregate |
| `get_uncommitted_events()` + `clear_events()` (separate) | SymbolAggregate, QuoteAggregate, OHLCVAggregate |

Recommend standardizing to `collect_events()` (single method, less error-prone). But this is optional cleanup -- do only if simple.

## Implementation Steps

1. Run `rg "pydantic" src/domain/` -- must be zero
2. Run `ruff check src/domain/ && ruff format --check src/domain/`
3. Run `pyright src/domain/`
4. Run `pyright src/persistence/schemas/`
5. Run `pytest -x --tb=short`
6. Apply `dataclasses.replace()` simplification in SymbolAggregate
7. (Optional) Standardize event collection methods
8. Final lint + type check + test pass

## Todo

- [x] Verify zero Pydantic imports in domain/
- [x] ruff check passes
- [x] pyright passes on domain/ and persistence/schemas/
- [x] Full test suite passes
- [x] Apply replace() simplification in SymbolAggregate
- [x] (Optional) Standardize event collection pattern
- [x] Update docs/code-standards.md to reflect dataclass domain pattern

## Success Criteria
- `rg "pydantic" src/domain/` returns zero matches
- All linting and type checking passes
- All tests pass
- Domain layer has zero framework dependencies (only stdlib)
