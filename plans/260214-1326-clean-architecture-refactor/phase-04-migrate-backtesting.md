# Phase 4: Migrate Backtesting

## Context
- [Brainstorm](../reports/brainstorm-260214-1326-clean-architecture-refactor.md)
- [Phase 3](./phase-03-migrate-strategy.md) must complete first

## Overview
- **Priority:** P1
- **Status:** Completed
- **Effort:** 4h
- **Description:** Migrate `features/backtesting/base/` — complex with engines, metrics, optimizer, repository, models. `performance_calculator.py` is pure domain; rest is I/O-heavy application/infrastructure.

## Key Insights
- `performance_calculator.py` — PURE (numpy only) → new `domain/backtest/services/`
- `backtest_runner.py` — I/O heavy (DB, EventBus, PaperBroker) → `application/backtesting/`
- `historical_replay_engine.py` — MIXED (EventBus + replay logic) → `application/backtesting/` (keep whole, not worth splitting)
- `result_collector.py` — MIXED (simulation time I/O + trade math) → `application/backtesting/` (keep whole)
- `grid_optimizer.py` — I/O (asyncio, logging, PaperBroker) → `application/backtesting/`
- `backtest_repository.py` — MongoDB persistence → `infrastructure/persistence/repositories/`
- `models/*` — DTOs stay in features per brainstorm decision. BUT: BacktestConfig/BacktestResult are used by application services, not just handlers. Create shared DTOs accessible from application layer.

## Architecture

```
BEFORE:                                  AFTER:
features/backtesting/                    features/backtesting/
├── base/                                ├── router.py
│   ├── engine/                          ├── run/       {command, handler, route}
│   │   ├── backtest_runner.py           ├── optimize/  {command, handler, route}
│   │   └── historical_replay_engine.py  ├── get_result/ {query, handler}
│   ├── metrics/                         ├── list_results/ {query, handler}
│   │   ├── performance_calculator.py    └── get_optimization/ {query, handler}
│   │   └── result_collector.py
│   ├── models/                          domain/backtest/
│   │   ├── backtest_config.py           └── services/
│   │   ├── backtest_result.py               └── performance_calculator.py
│   │   ├── optimization_config.py
│   │   └── optimization_result.py       application/backtesting/
│   ├── optimizer/                       ├── backtest_runner.py
│   │   └── grid_optimizer.py            ├── historical_replay_engine.py
│   └── repository/                      ├── result_collector.py
│       └── backtest_repository.py       ├── grid_optimizer.py
├── router.py                            └── models/
├── run/                                     ├── backtest_config.py
├── optimize/                                ├── backtest_result.py
├── get_result/                              ├── optimization_config.py
├── list_results/                            └── optimization_result.py
└── get_optimization/
                                         infrastructure/persistence/repositories/
                                         └── backtest_repository.py
```

**Note on models:** Backtesting models (config, result) are used by both handlers AND application services (runner, optimizer, collector). Moving them to `application/backtesting/models/` keeps them accessible to both layers without polluting domain with Pydantic DTOs.

## Related Code Files

### Move to domain
- `src/features/backtesting/base/metrics/performance_calculator.py` → `src/domain/backtest/services/performance_calculator.py`

### Move to application
- `src/features/backtesting/base/engine/backtest_runner.py` → `src/application/backtesting/backtest_runner.py`
- `src/features/backtesting/base/engine/historical_replay_engine.py` → `src/application/backtesting/historical_replay_engine.py`
- `src/features/backtesting/base/metrics/result_collector.py` → `src/application/backtesting/result_collector.py`
- `src/features/backtesting/base/optimizer/grid_optimizer.py` → `src/application/backtesting/grid_optimizer.py`
- `src/features/backtesting/base/models/backtest_config.py` → `src/application/backtesting/models/backtest_config.py`
- `src/features/backtesting/base/models/backtest_result.py` → `src/application/backtesting/models/backtest_result.py`
- `src/features/backtesting/base/models/optimization_config.py` → `src/application/backtesting/models/optimization_config.py`
- `src/features/backtesting/base/models/optimization_result.py` → `src/application/backtesting/models/optimization_result.py`

### Move to infrastructure
- `src/features/backtesting/base/repository/backtest_repository.py` → `src/infrastructure/persistence/repositories/backtest_repository.py`

### Modify (update imports)
- `src/features/backtesting/run/handler.py`
- `src/features/backtesting/optimize/handler.py`
- `src/features/backtesting/get_result/handler.py`
- `src/features/backtesting/list_results/handler.py`
- `src/features/backtesting/get_optimization/handler.py`
- `src/application/backtesting/backtest_runner.py` (internal imports after move)
- `src/application/backtesting/grid_optimizer.py` (internal imports after move)
- `src/application/backtesting/result_collector.py` (internal imports after move)

### Create
- `src/application/backtesting/models/__init__.py`
- `src/domain/backtest/services/performance_calculator.py`

### Delete
- `src/features/backtesting/base/` (entire directory)

## Implementation Steps

1. **Move performance_calculator to domain**
   - Copy to `src/domain/backtest/services/performance_calculator.py`
   - Verify: only imports `numpy` — pure domain service
   - Update `__init__.py` exports

2. **Move models to application/backtesting/models/**
   - Create `src/application/backtesting/models/` with `__init__.py`
   - Copy all 4 model files (backtest_config, backtest_result, optimization_config, optimization_result)
   - These are Pydantic/dataclass DTOs shared between handlers and services
   - Update any internal cross-references between models

3. **Move repository to infrastructure**
   - Copy `backtest_repository.py` → `src/infrastructure/persistence/repositories/`
   - Update imports: `src.features.backtesting.base.models.backtest_result` → `src.application.backtesting.models.backtest_result`

4. **Move engines to application**
   - Copy `backtest_runner.py` → `src/application/backtesting/`
   - Copy `historical_replay_engine.py` → `src/application/backtesting/`
   - Update internal imports:
     - models: `src.features.backtesting.base.models` → `src.application.backtesting.models`
     - repository: `src.features.backtesting.base.repository` → `src.infrastructure.persistence.repositories`
     - result_collector: update after it's moved
     - market_data models: `src.features.market_data.base.models.ohlcv` → will be updated in phase 5, use current path for now

5. **Move result_collector to application**
   - Copy to `src/application/backtesting/result_collector.py`
   - Update: `performance_calculator` → `src.domain.backtest.services.performance_calculator`
   - Update: models → `src.application.backtesting.models`

6. **Move grid_optimizer to application**
   - Copy to `src/application/backtesting/grid_optimizer.py`
   - Update: `backtest_runner` → `src.application.backtesting.backtest_runner`
   - Update: models → `src.application.backtesting.models`

7. **Update handler imports**
   - All 5 handlers: replace `from src.features.backtesting.base` with:
     - Models: `from src.application.backtesting.models`
     - Runner: `from src.application.backtesting.backtest_runner`
     - Optimizer: `from src.application.backtesting.grid_optimizer`
     - Repository: `from src.infrastructure.persistence.repositories.backtest_repository`

8. **Search & fix ALL remaining references**
   - `grep -r "features.backtesting.base" src/` → must return zero

9. **Delete `features/backtesting/base/`**

10. **Verify**
    - Import checks for all moved modules
    - Run backtesting tests
    - Domain purity check: `grep -r "import.*common\|import.*infrastructure" src/domain/backtest/` → nothing

## Todo List
- [ ] Move performance_calculator to domain/backtest/services/
- [ ] Move models to application/backtesting/models/
- [ ] Move backtest_repository to infrastructure/persistence/repositories/
- [ ] Move backtest_runner to application/backtesting/
- [ ] Move historical_replay_engine to application/backtesting/
- [ ] Move result_collector to application/backtesting/
- [ ] Move grid_optimizer to application/backtesting/
- [ ] Update all 5 handler imports
- [ ] Fix all remaining `features.backtesting.base` references
- [ ] Delete features/backtesting/base/
- [ ] Verify domain purity
- [ ] Run tests

## Success Criteria
- `features/backtesting/` contains ONLY: router.py, 5 operation dirs
- `domain/backtest/services/performance_calculator.py` has zero I/O imports
- `application/backtesting/` has runner, replay engine, collector, optimizer, models/
- Repository in `infrastructure/persistence/repositories/`
- Zero `features.backtesting.base` references
- All tests pass

## Risk Assessment
- **Model location** — Models used by both handlers and services. Placing in application/ is pragmatic but slightly breaks "DTOs stay in features" decision. Acceptable trade-off: these are shared contracts, not API-specific DTOs.
- **Cross-feature deps** — `historical_replay_engine` imports from `market_data/base/models/ohlcv`. Will still reference old path until phase 5. Temporary coupling acceptable.
- **Performance calculator** — Pure numpy. If future needs require I/O (e.g., loading benchmark data), it must stay in application. Currently safe for domain.
