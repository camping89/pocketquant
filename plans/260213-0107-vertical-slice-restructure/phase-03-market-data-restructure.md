# Phase 3: Market Data Restructure

## Priority: High | Effort: High | Risk: High

Most complex feature. Sub-features (quotes, ohlcv, sync, status) already follow operation pattern internally. Main work: move infra to base/, extract inline routes from `api/routes.py`, create router.py tree.

## Context

- [Plan](plan.md) | Depends on: Phase 2
- `quotes/` already follows gold-standard pattern — mostly untouched
- `api/routes.py` has 166 LOC of inline endpoints that must be extracted

## Current → Target

```
market_data/                       market_data/
├── api/                           ├── router.py  (top-level aggregator)
│   ├── __init__.py                ├── base/
│   ├── routes.py (166 LOC inline) │   ├── __init__.py
│   └── quote_routes.py           │   ├── managers/
├── managers/                      │   │   ├── bar_manager.py
│   ├── bar_manager.py             │   │   └── bar_builder.py
│   └── bar_builder.py             │   ├── models/
├── models/                        │   │   ├── ohlcv.py
│   ├── ohlcv.py                   │   │   ├── quote.py
│   ├── quote.py                   │   │   └── symbol.py
│   └── symbol.py                  │   ├── providers/
├── providers/                     │   │   └── (existing files)
│   └── ...                        │   ├── services/
├── services/                      │   │   └── (existing files)
│   └── ...                        │   └── jobs/
├── jobs/                          │       └── sync_jobs.py
│   └── sync_jobs.py               ├── quotes/
├── quotes/ (already good)         │   ├── router.py  (from api/quote_routes.py)
│   ├── get_all/                   │   ├── dto.py
│   ├── get_latest/                │   ├── quote_service.py
│   ├── start_feed/                │   ├── get_all/
│   ├── stop_feed/                 │   ├── get_latest/
│   ├── subscribe/                 │   ├── get_current_bar/
│   ├── unsubscribe/               │   ├── start_feed/
│   └── get_current_bar/           │   ├── stop_feed/
├── ohlcv/                         │   ├── subscribe/
│   ├── dto.py                     │   └── unsubscribe/
│   └── get_ohlcv/                 ├── ohlcv/
├── sync/                          │   ├── router.py  (NEW - extract from api/routes.py)
│   ├── dto.py                     │   ├── dto.py
│   ├── sync_one/                  │   └── get_ohlcv/
│   └── sync_bulk/                 ├── sync/
├── status/                        │   ├── router.py  (NEW - extract from api/routes.py)
│   ├── dto.py                     │   ├── dto.py
│   ├── get_quote_service_status/  │   ├── sync_one/
│   ├── get_symbol_sync_status/    │   └── sync_bulk/
│   └── get_sync_status/           └── status/
└── __init__.py                        ├── router.py  (NEW - extract from api/routes.py)
                                       ├── dto.py
                                       ├── get_quote_service_status/
                                       ├── get_symbol_sync_status/
                                       └── get_sync_status/
```

## Inline Endpoints to Extract

`api/routes.py` currently has these inline endpoints. Each needs a `route.py` in its operation folder:

| Endpoint | Target Operation | Notes |
|----------|-----------------|-------|
| `POST /sync` | `sync/sync_one/route.py` | Already has command+handler, just needs route |
| `POST /sync/background` | `sync/sync_one/route.py` | Same operation, background variant |
| `POST /sync/bulk` | `sync/sync_bulk/route.py` | Already has command+handler |
| `GET /ohlcv/{exchange}/{symbol}` | `ohlcv/get_ohlcv/route.py` | Already has query+handler |
| `GET /symbols` | `list_symbols/route.py` (NEW) | Direct DB query, no mediator. Create new operation |
| `GET /sync-status` | `status/get_sync_status/route.py` | Already has query+handler |
| `GET /sync-status/{exchange}/{symbol}` | `status/get_symbol_sync_status/route.py` | Already has query+handler |

## Files to Modify

**Move (git mv):**
- `managers/` → `base/managers/`
- `models/` → `base/models/`
- `providers/` → `base/providers/`
- `services/` → `base/services/`
- `jobs/` → `base/jobs/`

**Create:**
- `router.py` — top-level aggregator, collects sub-feature routers
- `quotes/router.py` — from `api/quote_routes.py` content (move status endpoint to status/)
- `ohlcv/router.py` — NEW, collects get_ohlcv route
- `sync/router.py` — NEW, collects sync_one and sync_bulk routes
- `status/router.py` — NEW, collects 3 status operation routes
- `sync/sync_one/route.py` — extract from api/routes.py
- `sync/sync_bulk/route.py` — extract from api/routes.py
- `ohlcv/get_ohlcv/route.py` — extract from api/routes.py
- `status/get_sync_status/route.py` — extract from api/routes.py
- `status/get_symbol_sync_status/route.py` — extract from api/routes.py
- `list_symbols/` — NEW operation (query.py, handler.py, route.py)
- `base/__init__.py` — re-export key classes

**Delete:**
- `api/` folder entirely

**Update:**
- `__init__.py` — minimal, just docstring
- `base/managers/bar_manager.py` — imports from models → base.models
- `base/managers/bar_builder.py` — imports from models → base.models
- `base/jobs/sync_jobs.py` — imports from models → base.models, sync → sync
- `quotes/` internal imports — models path change (models → base.models)
- `ohlcv/` internal imports — same
- `sync/` internal imports — same
- `status/` internal imports — same

## Import Changes (key ones)

| Old Path | New Path |
|----------|----------|
| `src.features.market_data.api.routes` | `src.features.market_data.router` |
| `src.features.market_data.api.quote_routes` | `src.features.market_data.quotes.router` |
| `src.features.market_data.models.*` | `src.features.market_data.base.models.*` |
| `src.features.market_data.managers.*` | `src.features.market_data.base.managers.*` |
| `src.features.market_data.jobs.*` | `src.features.market_data.base.jobs.*` |
| `src.features.market_data.providers.*` | `src.features.market_data.base.providers.*` |
| `src.features.market_data.services.*` | `src.features.market_data.base.services.*` |

### Cross-feature (update immediately)

- `src.infrastructure.tradingview.provider` imports `src.features.market_data.models.ohlcv` → update to `src.features.market_data.base.models.ohlcv`
- `src.infrastructure.tradingview.base` imports `src.features.market_data.models.ohlcv` → same
- `src.features.backtesting.base.engine.backtest_runner` imports `src.features.market_data.models.ohlcv` → same
- `src.features.backtesting.base.engine.historical_replay_engine` imports `src.features.market_data.models.ohlcv` → same

## Implementation Steps

1. Create `base/` with sub-folders: `managers/`, `models/`, `providers/`, `services/`, `jobs/`
2. `git mv` each infra folder's contents into `base/` sub-folders
3. Create `base/__init__.py` with re-exports for commonly used classes
4. Extract inline endpoints from `api/routes.py` into per-operation `route.py` files
5. Create `list_symbols/` as new operation (move inline DB query into handler)
6. Create sub-feature `router.py` files (ohlcv, sync, status)
7. Move `api/quote_routes.py` logic into `quotes/router.py` (remove status glue endpoint — move to status/)
8. Create top-level `router.py` that collects all sub-feature routers
9. Update all internal imports (models → base.models, etc.)
10. Update cross-feature imports (tradingview, backtesting)
11. Delete `api/` folder
12. Run `ruff check` + `pyright`

## Router Tree

```python
# market_data/router.py
router = APIRouter(prefix="/market-data", tags=["Market Data"])
router.include_router(sync_router)       # from sync/router.py
router.include_router(ohlcv_router)      # from ohlcv/router.py
router.include_router(status_router)     # from status/router.py
router.include_router(symbols_router)    # from list_symbols/route.py

# quotes/router.py (separate prefix)
router = APIRouter(prefix="/quotes", tags=["Real-time Quotes"])
# ... collects quote operation routes

# main.py includes both: market_data/router.py and quotes/router.py
```

## Todo

- [x] Create base/ sub-folder structure
- [x] Move infra folders to base/
- [x] Extract inline endpoints from api/routes.py into operation route.py files
- [x] Create list_symbols operation
- [x] Create sub-feature router.py files
- [x] Create quotes/router.py from quote_routes.py
- [x] Create top-level router.py
- [x] Update all internal imports
- [x] Update cross-feature imports (tradingview, backtesting)
- [x] Delete api/ folder
- [x] Verify ruff + pyright pass

## Success Criteria

- All market_data imports resolve correctly
- No inline endpoints remain in monolithic route files
- Each sub-feature has its own `router.py`
- Top-level `router.py` cleanly aggregates sub-feature routers
- Cross-feature imports updated (tradingview, backtesting)
