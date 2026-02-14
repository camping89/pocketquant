# Brainstorm: Clean Architecture Refactor — Features → Layered Separation

**Date:** 2026-02-14 | **Status:** Agreed | **Branch:** feat/strategy-init

## Problem Statement

`src/features/` mixes two concerns:
1. **Operations** — commands, queries, handlers, routes (vertical slice entry points)
2. **Support code** — managers, engines, models, repositories, services (business logic + data access)

Goal: features should be **thin operation layers only**. Support code moves to proper Clean Architecture layers: domain, application, infrastructure.

## Agreed Decisions

| Decision | Choice |
|----------|--------|
| Target layers | Hybrid: managers→domain, repos→infrastructure, engines→application |
| DTOs/Pydantic models | Stay in features (operation contract) |
| Services/orchestrators | New `src/application/` layer |
| Mixed managers | Split: pure logic→domain, orchestration→application |
| Model duplication | Deduplicate now, single source of truth |
| Application layout | Per-feature (application/backtesting/, application/market_data/) |

## Target Architecture

```
src/
├── domain/                              # Pure business logic, NO I/O
│   ├── ohlcv/
│   │   └── services/
│   │       └── bar_builder.py           ← pure bar construction logic
│   ├── order/
│   │   └── services/
│   │       └── order_rules.py           ← pure order validation/rules
│   ├── position/
│   │   └── services/
│   │       └── position_rules.py        ← pure position logic
│   ├── strategy/
│   │   ├── strategy_interface.py        ← abstract contract
│   │   └── implementations/
│   │       └── ma_crossover.py          ← concrete strategy
│   ├── backtest/                        ← NEW aggregate
│   │   └── services/
│   │       └── performance_calculator.py
│   └── ...existing aggregates unchanged...
│
├── application/                         ← NEW LAYER (per-feature)
│   ├── backtesting/
│   │   ├── backtest_runner.py
│   │   ├── historical_replay_engine.py
│   │   ├── grid_optimizer.py
│   │   └── result_collector.py
│   ├── market_data/
│   │   ├── bar_manager.py               ← orchestration (calls domain + infra)
│   │   ├── quote_service.py
│   │   └── sync_jobs.py
│   ├── strategy/
│   │   ├── strategy_engine.py
│   │   └── yaml_loader.py
│   └── trading/
│       ├── order_manager.py             ← orchestration half
│       └── position_tracker.py
│
├── infrastructure/                      # Extended with repos from features
│   ├── persistence/
│   │   ├── repositories/
│   │   │   ├── backtest_repository.py
│   │   │   ├── order_repository.py
│   │   │   ├── position_repository.py
│   │   │   └── market_data_repositories.py
│   │   └── ...existing...
│   ├── providers/                       ← market data providers from features
│   └── ...existing unchanged...
│
├── features/                            # ONLY thin operations
│   ├── backtesting/
│   │   ├── router.py
│   │   ├── run/        {command, handler, route, dto}
│   │   ├── optimize/   {command, handler, route, dto}
│   │   ├── get_result/ {query, handler}
│   │   └── list_results/ {query, handler}
│   ├── market_data/    ← NO base/, NO repositories/
│   ├── strategy/       ← NO base/
│   ├── trading/        ← NO base/
│   └── risk/
│
├── common/              # Unchanged
└── main.py
```

## Dependency Direction (strict, enforced)

```
features/ ──→ application/ ──→ domain/
    │              │
    └──────────────┴──→ infrastructure/ ──→ domain/
```

- **domain/** imports NOTHING external (pure business logic)
- **infrastructure/** imports from domain (for interfaces/contracts)
- **application/** imports from domain + infrastructure
- **features/** imports from application + domain (for types/DTOs)
- **NEVER**: domain → infrastructure, domain → application, domain → features

## Migration Map

### backtesting/base/ → distributed

| File | Target | Reason |
|------|--------|--------|
| `engine/backtest_runner.py` | `application/backtesting/` | Orchestrates I/O + domain |
| `engine/historical_replay_engine.py` | `application/backtesting/` | Orchestrates replay logic |
| `metrics/performance_calculator.py` | `domain/backtest/services/` | Pure math, no I/O |
| `metrics/result_collector.py` | `application/backtesting/` | Collects from multiple sources |
| `optimizer/grid_optimizer.py` | `application/backtesting/` | Orchestrates multiple runs |
| `repository/backtest_repository.py` | `infrastructure/persistence/repositories/` | Data access |
| `models/*` | stays in features as DTOs | Operation contracts |

### market_data/base/ → distributed

| File | Target | Reason |
|------|--------|--------|
| `managers/bar_builder.py` | split: pure→`domain/ohlcv/services/`, orchestration→`application/market_data/` | Mixed concern |
| `managers/bar_manager.py` | `application/market_data/` | Stateful orchestrator with I/O |
| `jobs/sync_jobs.py` | `application/market_data/` | Background orchestration |
| `providers/*` | `infrastructure/providers/` | External I/O |
| `models/*` | deduplicate with `domain/` entities | Already exist in domain |
| `repositories/*` | `infrastructure/persistence/repositories/` | Data access |
| `quotes/quote_service.py` | `application/market_data/` | Multi-concern orchestrator |

### strategy/base/ → distributed

| File | Target | Reason |
|------|--------|--------|
| `strategy_interface.py` | `domain/strategy/` | Pure abstract contract |
| `strategy_engine.py` | `application/strategy/` | Orchestrator with I/O |
| `strategy_config.py` | stays in features as DTO | Config model |
| `ma_crossover.py` | `domain/strategy/implementations/` | Pure strategy logic |
| `yaml_loader.py` | `application/strategy/` | File I/O involved |

### trading/base/ → distributed

| File | Target | Reason |
|------|--------|--------|
| `managers/order_manager.py` | split: rules→`domain/order/services/`, orchestration→`application/trading/` | Mixed |
| `managers/position_tracker.py` | split: rules→`domain/position/services/`, orchestration→`application/trading/` | Mixed |
| `repositories/order_repository.py` | `infrastructure/persistence/repositories/` | Data access |
| `repositories/position_repository.py` | `infrastructure/persistence/repositories/` | Data access |
| `models/*` | deduplicate with `domain/` entities | Already in domain |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Massive import changes | Every handler references `base/` | Incremental: one feature at a time |
| Circular dependencies | application↔features | Strict dependency direction, lint rule |
| Breaking tests | Integration tests touch moved modules | Run tests after each feature migration |
| Manager splitting bugs | Subtle logic corruption when splitting | Review each manager's I/O deps first |
| Model dedup confusion | Which model is canonical? | Domain entity = truth, feature DTO = API shape |

## Migration Order (recommended)

1. **trading/** — smallest (4 ops), clearest separation, good proof-of-concept
2. **risk/** — minimal (1 op, no base/ to move)
3. **strategy/** — medium complexity, clear domain/application split
4. **backtesting/** — complex engines/metrics but well-isolated
5. **market_data/** — largest (14 ops), most entangled (providers, jobs, services)

## Success Criteria

- [ ] `features/` contains ONLY: commands, queries, handlers, routes, DTOs, routers
- [ ] No `base/` directories remain in any feature
- [ ] `src/application/` exists with per-feature orchestrators
- [ ] All repositories live under `infrastructure/persistence/`
- [ ] Domain layer has zero I/O imports
- [ ] All existing tests pass after migration
- [ ] No circular imports between layers
- [ ] Dependency direction enforced: features→application→domain, infrastructure→domain
