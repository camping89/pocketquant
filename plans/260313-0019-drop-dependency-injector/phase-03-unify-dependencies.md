# Phase 3: Unify Depends() Functions

**Priority:** High | **Status:** Pending | **Effort:** S

## Overview

Merge the two existing `dependencies.py` files into one `src/dependencies.py`. Add Depends() functions for any service that routes need.

## Context Links

- Current: `src/common/mediator/dependencies.py` (11 LOC)
- Current: `src/features/market_data/quotes/dependencies.py` (12 LOC)
- All routes use `Annotated[Mediator, Depends(get_mediator)]` pattern

## Implementation Steps

1. Create `src/dependencies.py`:

```python
"""FastAPI Depends() functions — single source for all route injection."""

from typing import Annotated

from fastapi import Depends, Request

from src.common.mediator.mediator import Mediator
from src.application.market_data.quote_service import QuoteService
from src.services import Services


def get_services(request: Request) -> Services:
    """Get the Services registry from app state."""
    return request.app.state.services


def get_mediator(request: Request) -> Mediator:
    """Get Mediator instance for CQRS dispatch."""
    return request.app.state.services.mediator


def get_quote_service(request: Request) -> QuoteService:
    """Get QuoteService for quote operations."""
    return request.app.state.services.quote_service


# Type aliases for clean route signatures
MediatorDep = Annotated[Mediator, Depends(get_mediator)]
QuoteServiceDep = Annotated[QuoteService, Depends(get_quote_service)]
ServicesDep = Annotated[Services, Depends(get_services)]
```

2. Delete `src/common/mediator/dependencies.py`
3. Delete `src/features/market_data/quotes/dependencies.py`
4. Update all route imports:

**Find & replace across all route files:**
```
# Old imports (two different locations)
from src.common.mediator.dependencies import get_mediator
from src.features.market_data.quotes.dependencies import get_quote_service

# New import (one location)
from src.dependencies import get_mediator, get_quote_service
```

5. Routes themselves stay unchanged — they already use `Annotated[Mediator, Depends(get_mediator)]`

## Affected Route Files

All 28 route files under `src/features/` that import `get_mediator`:
- `src/features/market_data/sync/sync_one/route.py`
- `src/features/market_data/sync/sync_bulk/route.py`
- `src/features/market_data/ohlcv/get_ohlcv/route.py`
- `src/features/market_data/quotes/*/route.py` (7 files)
- `src/features/market_data/status/*/route.py` (3 files)
- `src/features/market_data/list_symbols/route.py`
- `src/features/backtesting/*/route.py` (5 files)
- `src/features/strategy/*/route.py` (5 files)
- `src/features/trading/*/route.py` (4 files)
- `src/features/risk/check_risk/route.py`

Quote-specific routes also import `get_quote_service`:
- `src/features/market_data/quotes/get_current_bar/route.py`

## Todo

- [ ] Create `src/dependencies.py`
- [ ] Delete `src/common/mediator/dependencies.py`
- [ ] Delete `src/features/market_data/quotes/dependencies.py`
- [ ] Update all route imports (grep for old import paths)
- [ ] Run `pyright` to verify no broken imports

## Success Criteria

- One `dependencies.py` file for all route injection
- All routes compile with updated imports
- No `resolve()` calls anywhere in Depends functions
- `pyright` passes
