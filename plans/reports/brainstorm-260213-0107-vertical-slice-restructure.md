# Brainstorm: Vertical Slice Restructure

## Problem

Inconsistent folder structure across features. `market_data/quotes/` uses operations at root (clean), while `strategy/` and `backtesting/` bury operations under `handlers/` wrapper (noisy). Infrastructure code (engine, loader, etc.) sits at same level as operations, making it hard to distinguish "what can I do?" from "how does it work?".

## Agreed Canonical Pattern

```
feature/
├── base/                ← ALL non-operation code (infra, models, services)
│   ├── engine/          ← sub-folders when 10+ files
│   ├── models/
│   └── config.py        ← flat files when few
├── operation_a/         ← CQRS operation (immediately visible)
│   ├── command.py       ← or query.py
│   ├── handler.py
│   ├── route.py         ← optional, only if HTTP-exposed
│   └── __init__.py
├── operation_b/
├── router.py            ← route aggregator (replaces api/ folder)
└── __init__.py
```

**Rules:**
- Operations = top-level folders (scannable from `ls`)
- Everything else = `base/` (config, engine, loader, models, repository, etc.)
- `api/` folder eliminated → replaced by `router.py` at feature root
- `handlers/` wrapper eliminated → operations promoted to root
- `base/` uses sub-folders when feature has 10+ infra files

## Target State Per Feature

### 1. Strategy

**Current → Target:**
```
strategy/                          strategy/
├── api/routes.py          →      ├── router.py
├── base/config,interface  →      ├── base/
├── engine/                →      │   ├── strategy_config.py
├── loader/                →      │   ├── strategy_interface.py
├── examples/              →      │   ├── strategy_engine.py
├── registry/              →      │   ├── yaml_loader.py
├── handlers/              →      │   ├── ma_crossover.py
│   ├── get_all/           →      │   └── registry/
│   ├── get_one/           →      ├── get_all/
│   ├── load/              →      ├── get_one/
│   ├── start/             →      ├── load/
│   └── stop/              →      ├── start/
                                  └── stop/
```

### 2. Backtesting

**Current → Target:**
```
backtesting/                       backtesting/
├── api/backtest_routes.py →      ├── router.py
├── engine/                →      ├── base/
├── metrics/               →      │   ├── engine/
├── optimizer/             →      │   ├── metrics/
├── repository/            →      │   ├── optimizer/
├── models/                →      │   ├── repository/
├── handlers/              →      │   └── models/
│   ├── run/               →      ├── run/
│   ├── get_result/        →      ├── get_result/
│   ├── list_results/      →      ├── list_results/
│   ├── optimize/          →      ├── optimize/
│   └── get_optimization/  →      └── get_optimization/
```

### 3. Market Data

Sub-features (quotes, ohlcv, sync, status) already follow operation pattern. Main changes:
- `api/routes.py` → `router.py` (collects sub-feature routers)
- `api/quote_routes.py` → `quotes/router.py`
- Inline endpoints in `api/routes.py` → move to per-operation `route.py` files
- `managers/`, `models/`, `providers/`, `services/`, `jobs/` → `base/`

```
market_data/                       market_data/
├── api/                   →      ├── router.py  (top-level aggregator)
│   ├── routes.py          →      ├── base/
│   └── quote_routes.py    →      │   ├── managers/
├── managers/              →      │   ├── models/
├── models/                →      │   ├── providers/
├── providers/             →      │   ├── services/
├── services/              →      │   └── jobs/
├── jobs/                  →      ├── quotes/
├── quotes/ (already good) →      │   ├── router.py
├── ohlcv/                 →      │   ├── get_all/
├── sync/                  →      │   ├── start_feed/
├── status/                →      │   └── ...
                                  ├── ohlcv/
                                  │   ├── router.py
                                  │   └── get_ohlcv/
                                  ├── sync/
                                  │   ├── router.py
                                  │   ├── sync_one/
                                  │   └── sync_bulk/
                                  └── status/
                                      ├── router.py
                                      └── get_sync_status/ ...
```

**Note:** `api/routes.py` has inline endpoints (sync, ohlcv, symbols, sync-status) that need extraction into per-operation route.py files.

### 4. Trading

Currently no operation folders — everything inline in `api/routes.py`. Also doesn't use mediator (uses `request.app.state` directly).

```
trading/                           trading/
├── api/routes.py          →      ├── router.py
├── managers/              →      ├── base/
├── models/                →      │   ├── managers/
├── repositories/          →      │   ├── models/
                                  │   └── repositories/
                                  ├── list_orders/
                                  ├── get_order/
                                  ├── list_positions/
                                  └── get_position/
```

**Open question:** Trading currently bypasses mediator. Convert to mediator pattern during this refactor, or keep it as-is and only restructure folders?

### 5. Risk

Minimal — single handler file. Not worth complex restructuring.

```
risk/                              risk/
├── handlers/              →      ├── base/
│   └── risk_check_handler.py →   │   └── (empty or risk models)
                                  └── check_risk/
                                      └── handler.py
```

## Key Observations

1. **`market_data/api/routes.py` is half-refactored** — sub-features have operation folders but routes are still inline in the monolithic file
2. **Trading skips mediator entirely** — uses `request.app.state` directly. Folder restructure can happen independently of mediator adoption
3. **`market_data/quotes/` is the gold standard** — already follows the target pattern perfectly
4. **Import paths change everywhere** — all `from src.features.X.handlers.Y` become `from src.features.X.Y`

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Mass import breakage | High | Systematic find-and-replace, test suite |
| `__init__.py` re-exports break | Medium | Update all `__init__.py` files carefully |
| Circular imports | Medium | base/ imports should never import from operations |
| Git history loss | Low | Use `git mv` for moves |
| main.py route registration breaks | High | Update after all features restructured |

## Recommended Execution Order

1. **Strategy** — smallest, most contained, proves the pattern
2. **Backtesting** — similar structure, validates pattern at scale
3. **Market Data** — most complex, extract inline routes
4. **Trading** — folder restructure only (mediator conversion separate)
5. **Risk** — trivial
6. **Fix all imports, __init__.py, main.py** — cross-cutting

## Next Steps

Create implementation plan with phases per feature, or proceed directly?
