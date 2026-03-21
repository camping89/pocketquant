# Brainstorm: Monorepo Package Split

**Date:** 2026-03-21 | **Status:** Approved | **Branch:** feat/strategy-init

---

## Problem Statement

PocketQuant is a single `src/` Python package. User wants .NET-style project separation: distinct packages for backtesting vs live trading vs shared core. Goals: mental clarity, independent usage (pip install backtest without API), team separation.

## Coupling Analysis (Scout Results)

| Module | Coupling to Trading | Isolation |
|--------|-------------------|-----------|
| domain/backtest/ | ZERO | PERFECT |
| domain/order/, position/ | self-contained | PERFECT |
| app/backtesting/ | ZERO (fresh PaperBroker) | GOOD |
| app/strategy/ | HIGH (intentional orchestrator) | COUPLED |
| concepts/strategy/, risk/ | ZERO | PERFECT |

Key insight: backtesting is already decoupled. Seams exist, this is a packaging exercise.

## Evaluated Approaches

### Option A: 3 Packages ❌ Rejected
- Core + Backtest + Trading
- Problem: trading owns API, must depend on backtest for route/DI wiring
- Muddies the independence boundary

### Option B: 2 Packages ❌ Rejected
- Main + Backtest extracted
- Too minimal, doesn't achieve full separation goals

### Option C: 4 Packages ✅ Chosen
- Core + Backtest + Trading + API
- Clean composition root pattern (API = .NET Web project)
- Backtest and Trading never depend on each other

## Final Architecture

```
Dependency Graph:

  pocketquant-core        (0 deps)
       ↑           ↑
       │           │
  backtest       trading
  (core)         (core)
       ↑           ↑
       │           │
       pocketquant-api
       (core + backtest + trading)
       [composition root]
```

### Package Ownership

| Package | Owns | Depends On |
|---------|------|------------|
| **core** | domain/{bar,symbol,sync_status,shared}, concepts/{strategy,risk,quote}, common/, persistence/, infrastructure/{tradingview,scheduling} | nothing |
| **backtest** | backtest domain (BacktestResult, Metrics), engine, PaperBroker, optimization, backtest handlers, BacktestAppService | core |
| **trading** | order domain, position domain, OKX broker, BrokerFactory, StrategyAppService, trading+strategy handlers | core |
| **api** | FastAPI routes, Dishka DI container, middleware, main.py, market_data app services | core, backtest, trading |

### Package Structure

```
pocketquant/
├── pyproject.toml                      # uv workspace root
├── packages/
│   ├── pocketquant-core/
│   │   ├── pyproject.toml
│   │   └── src/pocketquant/core/
│   │       ├── domain/
│   │       │   ├── bar/                # Bar entity, BarRepository interface
│   │       │   ├── symbol/             # Symbol entity, SymbolRepository
│   │       │   ├── sync_status/        # SyncStatus entity
│   │       │   └── shared/             # enums, events, value_objects
│   │       ├── concepts/
│   │       │   ├── strategy/           # IStrategy, Signal
│   │       │   ├── risk/               # PositionSizer, RiskModel
│   │       │   └── quote/              # Quote VO
│   │       ├── common/                 # mediator, cache, db, jobs, logging, etc.
│   │       ├── persistence/            # all MongoDB repositories
│   │       └── infrastructure/         # TradingView client, scheduling
│   │
│   ├── pocketquant-backtest/
│   │   ├── pyproject.toml              # depends: pocketquant-core
│   │   └── src/pocketquant/backtest/
│   │       ├── domain/                 # BacktestResult, OptimizationResult, Metrics
│   │       ├── engine/                 # backtest runner, historical replay
│   │       ├── brokers/                # PaperBroker (backtest-only)
│   │       ├── optimization/           # grid search, walk-forward
│   │       ├── handlers/               # 5 CQRS handlers
│   │       └── app_service.py          # BacktestAppService
│   │
│   ├── pocketquant-trading/
│   │   ├── pyproject.toml              # depends: pocketquant-core
│   │   └── src/pocketquant/trading/
│   │       ├── domain/
│   │       │   ├── order/              # OrderAggregate, events
│   │       │   └── position/           # PositionAggregate, events
│   │       ├── brokers/                # OKX broker, BrokerFactory
│   │       ├── strategy/               # StrategyAppService (orchestrator)
│   │       ├── handlers/               # trading + strategy CQRS handlers
│   │       └── app_services/           # OrderAppService, PositionAppService
│   │
│   └── pocketquant-api/
│       ├── pyproject.toml              # depends: core + backtest + trading
│       └── src/pocketquant/api/
│           ├── routes/                 # FastAPI route modules
│           ├── middleware/             # CORS, error handling, etc.
│           ├── di/                     # Dishka providers + container
│           └── main.py                 # uvicorn entrypoint
```

## Migration Strategy

| Phase | Action | Risk |
|-------|--------|------|
| 0 | Add import-linter, validate boundaries | None |
| 1 | Extract pocketquant-core | Medium (most files move) |
| 2 | Extract pocketquant-backtest | Low (already isolated) |
| 3 | Extract pocketquant-trading | Medium (strategy orchestration) |
| 4 | Remaining → pocketquant-api | Low (thin shell) |

Each phase: move files → fix imports → `uv sync` → run tests → commit.

## Risks & Mitigations

1. **Import path changes** — every `from src.` becomes `from pocketquant.core.` / `from pocketquant.backtest.` etc. Mitigate: sed/find-replace per phase, run pyright after.
2. **DI container split** — currently 6 providers in one container. Each package may expose its own provider; API assembles them. Mitigate: provider-per-package pattern.
3. **Circular imports** — StrategyAppService uses TYPE_CHECKING for OrderAppService. Both in trading package now, so circularity stays contained.
4. **Test restructuring** — tests/ must mirror package structure. Mitigate: move tests alongside each package.

## Success Criteria

- [ ] `uv sync --package pocketquant-core` works standalone
- [ ] `uv sync --package pocketquant-backtest` works without trading installed
- [ ] `uv run --package pocketquant-api` starts the server
- [ ] All existing tests pass
- [ ] import-linter contracts pass (backtest ⊥ trading)

## Tooling

- **uv workspaces** for package management
- **import-linter** for architectural boundary enforcement in CI
- **Namespace packages** (`pocketquant.*`) for unified import namespace

## Next Steps

→ Create detailed implementation plan via /ck:plan
